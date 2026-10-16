// The black hole behind the hero, ray traced live: every pixel's light is bent around the hole (Schwarzschild),
// so the lensing, the photon ring and the brighter approaching side come out of the physics. The gas streams
// round, inner lanes faster than outer ones, and the camera eases toward the cursor. No WebGL: the poster stays.
(() => {
  const cv = document.getElementById("hole");
  if (!cv) return;
  const gl = cv.getContext("webgl", { antialias: false, alpha: false, depth: false, powerPreference: "high-performance" });
  if (!gl) { cv.parentNode.classList.add("still"); return; }
  const FS = `
    precision highp float;
    uniform vec2 uRes; uniform float uT; uniform vec2 uLook; uniform float uZoom; uniform float uRoll; uniform vec2 uShift; uniform float uDist; uniform float uPix;
    float hash3(vec3 p){ p = fract(p * .3183099 + .1); p *= 17.; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
    float noise3(vec3 x){ vec3 i = floor(x), f = fract(x); f = f * f * (3. - 2. * f);
      return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x), mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
                 mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x), mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z); }
    float shash(vec3 p){ return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
    // the sky, looked up by direction, so the lensing has no seam to bend into a ring
    vec3 sky(vec3 d){
      vec3 c = vec3(0.);
      for (int L = 0; L < 3; L++) {
        float sc = 90. + float(L) * 120.;
        vec3 g = d * sc, id = floor(g);
        float h = shash(id + float(L) * 13.1);
        if (h > .86) {
          vec3 o = vec3(shash(id + 1.3), shash(id + 5.9), shash(id + 9.4));
          float r = length(d - normalize(id + o)) * sc;
          c += vec3(smoothstep(.14 - float(L) * .03, .0, r) * (.25 + (h - .86) * 6.));
        }
      }
      return c;
    }
    // the gas: fine lanes along the orbit, spaced by log radius. A lane finer than the pixel it lands in fades out
    // instead of flickering (fp: how much radius one pixel covers where the ray meets the disk)
    float lanes(float pr, float ang, float fp){
      vec2 cs = vec2(cos(ang), sin(ang));
      float l = log(pr), q = fp / pr * 2.;   // fade early: soft, blended streaks
      float s = noise3(vec3(l * 4., cs * 1.3));
      s += (noise3(vec3(l * 14., cs * 1.8 + 3.)) - .5) * .32 * smoothstep(.04, .015, q);
      s += (noise3(vec3(l * 45., cs * 2.4 + 7.)) - .5) * .25 * smoothstep(.012, .005, q);
      s += (noise3(vec3(l * 130., cs * 3. + 11.)) - .5) * .2 * smoothstep(.004, .0015, q);
      return clamp(s, 0., 1.);
    }
    // two copies of the lanes, each sheared by the orbit for one period and faded out as the other fades in,
    // so the gas streams for ever without winding up into noise
    float gas(float pr, float ang, float fp){
      float w = sqrt(.5 / (pr * pr * pr)) * 2.4, P = 14.;
      float p1 = fract(uT / P), p2 = fract(uT / P + .5);
      float k = 1. - abs(2. * p1 - 1.);
      float s = mix(lanes(pr, ang - w * (p2 - .5) * P + 2.1, fp), lanes(pr, ang - w * (p1 - .5) * P, fp), k);
      return clamp((s - .5) * (1. + .6 * k * (1. - k) * 4.) + .5, 0., 1.);   // two blended copies lose contrast: give it back
    }
    void main(){
      vec2 uv = (gl_FragCoord.xy - .5 * uRes) / uRes.y - uShift;
      uv *= uZoom;
      uv = mat2(cos(uRoll), sin(uRoll), -sin(uRoll), cos(uRoll)) * uv;
      float pitch = uLook.y, yaw = uLook.x;
      vec3 ro = vec3(sin(yaw) * cos(pitch), sin(pitch), -cos(yaw) * cos(pitch)) * uDist;
      vec3 fw = normalize(-ro), rt = normalize(cross(vec3(0., 1., 0.), fw)), up = cross(fw, rt);
      vec3 vel = normalize(fw * 2. + rt * uv.x + up * uv.y), pos = ro, v0 = vel;
      // rays that pass wide are bent once, analytically; the rest are traced
      vec3 cp = pos - vel * dot(pos, vel);
      bool near = length(cp) < 30.;
      if (!near) vel = normalize(vel - normalize(cp) * 2. / length(cp));
      float h2 = dot(cross(pos, vel), cross(pos, vel)), glow = 0., trav = 0., a = 0.;
      vec3 col = vec3(0.); bool fell = false;
      // the disk is a thin sheet: wherever the bent ray crosses the plane it picks up that ring's light
      if (near) for (int i = 0; i < 160; i++) {
        float r2 = dot(pos, pos), r = sqrt(r2);
        if (r < 1.) { fell = true; break; }
        float dt = clamp(.07 * r * r / (r + 2.), .01, 2.5);
        if (abs(pos.y) < .2 + .1 * length(pos.xz)) dt = min(dt, .1 + .03 * r);   // short steps through the disk: no sheet is skipped
        vec3 p0 = pos;
        vel += -1.5 * h2 * pos / (r2 * r2 * r) * dt;
        pos += vel * dt; trav += dt;
        glow += dt * exp(-pow((r - 1.53) * 12., 2.));
        // the disk is a few thin sheets stacked through its flaring thickness: puffy edge-on, still crisp
        float h0 = .03 + .04 * length(p0.xz), h1 = .03 + .04 * length(pos.xz);
        for (int k = -2; k <= 2; k++) {
          float f0 = p0.y - float(k) * h0, f1 = pos.y - float(k) * h1;
          if (f0 * f1 < 0.) {
            vec3 pc = mix(p0, pos, f0 / (f0 - f1));
            float pr = length(pc.xz), x = pr - 1.25;
            if (x > 0. && pr < 22.) {
              vec3 d = normalize(vel);
              float vy = max(abs(d.y), .05);
              float s = gas(pr, atan(pc.z, pc.x) + float(k) * 1.7, trav * uPix / vy);
              float wk = k == 0 ? 1. : (k == 1 || k == -1) ? .5 : .25;
              float prof = smoothstep(0., .8, x) * (exp(-x / .85) + exp(-x / 8.) * .27 * mix(1., smoothstep(.25, .06, vy), smoothstep(0., 3., dot(pc.xz, normalize(ro.xz))))) * smoothstep(22., 2., pr) * wk;
              float al = 1. - exp(-prof * (.35 + .8 * s * s) * .3 / pow(vy, 1.5));   // seen edge-on a sheet is thick: denser, brighter
              vec3 orbit = normalize(vec3(-pc.z, 0., pc.x));
              float dop = 1. / (1. - sqrt(.5 / pr) * dot(orbit, -d));
              vec3 src = (.63 + .65 * s) * pow(dop, 2.) * (.55 + exp(-x / 2.5)) * mix(vec3(1.), vec3(1., .95, .86), exp(-x * .6));
              col += (1. - a) * al * src; a += (1. - a) * al;
            }
          }
        }
        if (a > .99) break;
        if (r > 40. && dot(pos, vel) > 0.) break;
      }
      // the sky is only partly bent: full bending smears every star on the screen into an arc
      if (!fell) col += (1. - a) * (sky(normalize(mix(v0, normalize(vel), .12))) * smoothstep(.8, .32, length(normalize(vel) - v0)) + vec3(1., .95, .87) * glow * .25);
      col = 1. - exp(-col * 1.);
      gl_FragColor = vec4(col * vec3(.93, .95, .98), 1.);   // a cool silver, not a pure white
    }`;
  const VS = "attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }";
  const sh = (t, src) => { const o = gl.createShader(t); gl.shaderSource(o, src); gl.compileShader(o); if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw gl.getShaderInfoLog(o); return o; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer()); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = (n) => gl.getUniformLocation(pr, n);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // the frame: wide screens see more of the band, tall ones get the hole bigger and higher, over the words
  let q = 1, W = 0, H = 0;
  const Q = new URLSearchParams(location.search), DIST = +(Q.get("d") || 30);
  function size() {
    const r = cv.getBoundingClientRect(), d = Math.min(Math.min(1.5, devicePixelRatio || 1) * .75, Math.sqrt(5e5 / (r.width * r.height || 1))) * q;   // at most 0.5 MP: the gas is soft, the stars still read
    W = Math.max(1, Math.round(r.width * d)); H = Math.max(1, Math.round(r.height * d));
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    const tall = r.height > r.width;
    gl.viewport(0, 0, W, H);
    gl.uniform2f(U("uRes"), W, H);
    const A = Math.max(.5, Math.min(2.4, r.width / r.height));
    gl.uniform1f(U("uZoom"), .2 * 160 / DIST / A * (A > 1 ? 1.15 : .9));
    gl.uniform1f(U("uDist"), DIST);
    gl.uniform1f(U("uPix"), .2 * 160 / DIST / A * (A > 1 ? 1.15 : .9) / (2 * H));
    gl.uniform2f(U("uShift"), 0, tall ? .118 : .25);
  }
  // the camera eases toward the cursor: up flattens the disk, down tips it toward you. It never goes fully edge-on,
  // where the disk's sheets would show as lines
  let tx = .5, ty = .75, mx = tx, my = ty;
  addEventListener("pointermove", (e) => { tx = e.clientX / innerWidth; ty = e.clientY / innerHeight; }, { passive: true });
  let on = true, last = 0, slow = 0, t0 = performance.now();
  function frame(now) {
    mx += (tx - mx) * .04; my += (ty - my) * .04;
    gl.uniform1f(U("uT"), reduce ? 6 : (now - t0) / 1000 + 6);
    gl.uniform2f(U("uLook"), (mx - .5) * .2, .06 + .07 * my);
    gl.uniform1f(U("uRoll"), .2);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    // a slow GPU draws fewer pixels rather than a choppy hole
    if (last) { const ms = now - last; slow = ms > 24 && ms < 200 ? slow + 1 : Math.max(0, slow - 1); if (slow > 30 && q > .6) { q -= .1; slow = 0; size(); } }
    last = now;
    if (on && !reduce) requestAnimationFrame(frame);
  }
  size(); addEventListener("resize", size);
  new IntersectionObserver(([e]) => { const was = on; on = e.isIntersecting; if (on && !was) { last = 0; requestAnimationFrame(frame); } }).observe(cv);
  requestAnimationFrame((t) => { frame(t); cv.classList.add("on"); });
})();
