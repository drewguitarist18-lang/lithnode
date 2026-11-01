// The black hole behind the hero, ray traced live. Every pixel's light is bent around the hole (Schwarzschild), so the
// shadow, the far side of the disk lensed up over the top and down under the bottom, and the brighter side that comes
// toward you all fall out of the physics. The disk is a thin glowing slab of soft, streaming gas, warm white inside
// and cooler outside, with a faint haze round it. The camera drifts and leans toward the cursor, and the cursor bends
// the picture under it. No WebGL: the poster stays.
(() => {
  const cv = document.getElementById("hole");
  if (!cv) return;
  const gl = cv.getContext("webgl", { antialias: false, alpha: false, depth: false, powerPreference: "high-performance" });
  if (!gl) { cv.parentNode.classList.add("still"); return; }
  const FS = `
    precision highp float;
    uniform vec2 uC; uniform float uK, uT; uniform vec3 uCam; uniform vec4 uM;
    float sq(float x){ return x * x; }
    float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    float hash3(vec3 p){ p = fract(p * .3183099 + .1); p *= 17.; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
    float noise3(vec3 x){ vec3 i = floor(x), f = fract(x); f = f * f * (3. - 2. * f);
      return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x), mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
                 mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x), mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z); }
    float erf1(float x){ float t = x * x; return sign(x) * sqrt(1. - exp(-t * (1.2732 + .147 * t) / (1. + .147 * t))); }
    // how much gas at each radius: none inside 2, full by 2.75, thinning outward and gone by 17
    float dens(float r){ return smoothstep(2., 2.75, r) * smoothstep(17., 5., r) * pow(2.8 / r, 1.5); }
    // the gas: lumpy clouds in a frame that turns with the orbit (inner gas faster). Left alone the shear would wind
    // the clouds into thin rings, so two copies half a cycle apart take turns, each fading out before it winds up
    float clouds(vec3 s){ return .55 * noise3(s) + .3 * noise3(s * 2.1 + 3.7) + .15 * noise3(s * 4.3 + 11.); }
    float gas(vec2 xz, float r){
      float spin = 1.6 / pow(r, 1.5) + .1, a = atan(xz.y, xz.x), P = 9.;
      float f = fract(uT / P), g = fract(uT / P + .5), a1 = a + f * P * spin, a2 = a + g * P * spin;
      float k = abs(2. * f - 1.);   // 1 when copy one restarts: then it's all copy two
      float n = mix(clouds(vec3(cos(a1) * r * .4, sin(a1) * r * .4, r * .7)), clouds(vec3(cos(a2) * r * .4, sin(a2) * r * .4, r * .7) + 19.), k);
      n = clamp((n - .5) * 1.3 / sqrt(k * k + (1. - k) * (1. - k)) + .5, 0., 1.);   // a blend of two is flatter than either: undo that
      return .15 + 1.9 * n * n;
    }
    // the stars: round dots a pixel or two across, scattered on the six faces of a cube round the sky, three sizes
    float stars(vec3 d){
      vec3 a = abs(d);
      vec2 f; float face;
      if (a.x > a.y && a.x > a.z) { f = d.yz / a.x; face = d.x > 0. ? 0. : 1.; }
      else if (a.y > a.z) { f = d.xz / a.y; face = d.y > 0. ? 2. : 3.; }
      else { f = d.xy / a.z; face = d.z > 0. ? 4. : 5.; }
      float c = 0.;
      for (int L = 0; L < 3; L++) {
        float l = float(L), n = 125. / pow(2.4, l);
        vec2 g = f * n, id = floor(g) + face * 517. + l * 91.;
        float h = hash(id);
        if (h < .12 - .025 * l) {
          vec2 at = floor(g) + .5 + .3 * (vec2(hash(id + 2.3), hash(id + 5.9)) * 2. - 1.);
          float r = length(g - at) / n * .8, R = uK * (.65 + .4 * l);
          float tw = .78 + .22 * sin(uT * (1.2 + 2. * hash(id + 8.1)) + 40. * h);
          c += (.2 + .8 * pow(hash(id + 3.7), 3.)) * (.35 + .35 * l) * tw * exp(-sq(r / R));
        }
      }
      return c;
    }
    void main(){
      // the cursor is a small second mass: the picture under it bends (uM: where, in pixels; how much, 0..1; frame height)
      vec2 fc = gl_FragCoord.xy, dm = (fc - uM.xy) / uM.w;
      float m2 = dot(dm, dm);
      fc -= dm * uM.w * uM.z * .0042 / (m2 + .0064) * exp(-m2 / .08);
      vec2 q = (fc - uC) * uK;
      float cr = cos(uCam.z), sr = sin(uCam.z);
      q = vec2(cr * q.x + sr * q.y, cr * q.y - sr * q.x);
      // the camera: 19 out, a little above the disk, swung round by the yaw
      float cy = cos(uCam.x), sy = sin(uCam.x);
      vec3 ro = vec3(-19. * sy, uCam.y, -19. * cy), fw = normalize(-ro), rt = normalize(cross(vec3(0., 1., 0.), fw)), up = cross(fw, rt);
      vec3 v0 = normalize(fw + q.x * rt + q.y * up), v = v0, p = ro, am = cross(p, v);
      float h2 = dot(am, am), T = 1.;
      vec3 col = vec3(0.);
      bool fell = false;
      for (int i = 0; i < 260; i++) {
        float r = length(p);
        if (r < 1.) { fell = true; break; }
        if ((r > 17.5 && dot(p, v) > 0.) || T < .01) break;   // past the disk and leaving: nothing more to gather
        float rho = length(p.xz), hh = .05 + .022 * rho;
        bool near = abs(p.y) < 3.5 * hh + .4 && rho > 1.8 && rho < 16.;
        float dt = clamp(.09 * r * min(1., r / 3.), .02, 1.2);
        if (near) dt = min(dt, .3);
        vec3 pn = p + v * dt;
        v = normalize(v - 1.5 * h2 * p / pow(r, 5.) * dt);
        if (near || p.y * pn.y < 0.) {
          // the slab is Gaussian in height: take its mean over the step exactly (erf), so a coarse step stays smooth
          float y0 = p.y / hh, y1 = pn.y / hh;
          float w = abs(y1 - y0) > 1e-3 ? .8862269 * (erf1(y1) - erf1(y0)) / (y1 - y0) : exp(-y0 * y0);
          if (w > .003) {
            vec3 c = p.y * pn.y < 0. ? mix(p, pn, p.y / (p.y - pn.y)) : (abs(p.y) < abs(pn.y) ? p : pn);
            float rc = length(c.xz), pr = dens(rc);
            if (pr > .0005) {
              float d = w * pr * gas(c.xz, rc);
              float beam = sq(clamp(1. + .4 * dot(normalize(vec3(-c.z, 0., c.x)), -v), .4, 2.));   // gas coming toward you is brighter
              vec3 tint = mix(vec3(.8, .83, .9), vec3(1., .99, .97), smoothstep(6., 2.6, rc));
              col += T * d * beam * dt * 1.7 * tint;
              T *= exp(-d * dt * 2.4);
            }
          }
          col += T * exp(-sq(p.y / (hh * 3.))) * dens(rho) * dt * .009 * vec3(.85, .88, .95);   // a faint haze, like bloom
        }
        p = pn;
      }
      if (!fell) {
        // the photon ring: rays aimed just outside the critical impact parameter (3√3/2) circle the hole before they
        // escape. A crisp line there and a soft glow outside it, breathing slowly
        vec3 foot = ro - dot(ro, v0) * v0;
        float b = length(foot), x = b - 2.598;
        float ring = exp(-sq((x - .012) * 34.)) + .07 * exp(-x * 2.2);
        col += T * ring * (1. + .08 * sin(uT * .6)) * vec3(.94, .96, 1.);
        // the stars, bent part way by a closed form of the straight ray: round, never smeared into scratches
        float bend = .3 * (2. / b + 2.95 / (b * b));
        col += T * stars(v0 * cos(bend) - foot / b * sin(bend)) * smoothstep(2.8, 4.5, b);
      }
      col = clamp(col * (2.51 * col + .03) / (col * (2.43 * col + .59) + .14), 0., 1.);   // filmic: deep blacks, soft whites
      gl_FragColor = vec4(col + (hash(gl_FragCoord.xy) - .5) / 255., 1.);
    }`;
  const VS = "attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }";
  const sh = (t, src) => { const o = gl.createShader(t); gl.shaderSource(o, src); gl.compileShader(o); if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw gl.getShaderInfoLog(o); return o; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer()); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = (n) => gl.getUniformLocation(pr, n), uC = U("uC"), uK = U("uK"), uT = U("uT"), uCam = U("uCam"), uM = U("uM");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // the frame: at most 1.3 million pixels, and a slow GPU steps down from there. Wider than a phone, the hole's size
  // follows the width (up to a cap) and its middle sits 38% down below the 44px bar; on a phone it sits higher
  let q = 1;
  function size() {
    const r = cv.getBoundingClientRect(), w = r.width || 1, h = r.height || 1;
    const s = Math.min(devicePixelRatio || 1, Math.sqrt(1.3e6 / (w * h))) * q;
    const W = Math.max(1, Math.round(w * s)), H = Math.max(1, Math.round(h * s));
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    gl.viewport(0, 0, W, H);
    const phone = w < 640, zoom = phone ? .62 : Math.min(1.6, .9 * w / h);
    gl.uniform2f(uC, W / 2, H - (44 + (phone ? .26 : .38) * h) * s);
    gl.uniform1f(uK, 1 / (H * zoom));   // the view's slope per pixel
  }
  // the camera sways slowly and leans toward the cursor: left and right swing it round, down lifts it so the disk tips
  // toward you. With no cursor (a phone) it rests in the middle. Over the hole, the cursor also bends the picture under
  // it like a small lens that trails a little behind and swells in and out
  let tx = 0, ty = 0, mx = 0, my = 0, px = 0, py = 0, over = false, hx = .5, hy = .5, warp = 0;
  if (!reduce) {
    addEventListener("pointermove", (e) => {
      over = e.pointerType !== "touch";
      if (over) { tx = e.clientX / innerWidth * 2 - 1; ty = e.clientY / innerHeight * 2 - 1; px = e.clientX; py = e.clientY; }
    }, { passive: true });
    document.documentElement.addEventListener("pointerleave", () => { over = false; });
  }
  const t0 = performance.now();
  let on = true, last = 0, slow = 0;
  function draw(now) {
    const dt = last ? Math.min(.1, (now - last) / 1000) : 0, e = 1 - Math.exp(-dt * 3);
    mx += (tx - mx) * e; my += (ty - my) * e;
    const r = cv.getBoundingClientRect(), u = (px - r.left) / r.width, v = (py - r.top) / r.height;
    const inside = over && u >= 0 && u <= 1 && v >= 0 && v <= 1;
    if (inside && warp < .01) { hx = u; hy = v; }
    else if (inside) { const f = 1 - Math.exp(-dt * 21); hx += (u - hx) * f; hy += (v - hy) * f; }
    warp += (+inside - warp) * (1 - Math.exp(-dt * 5));
    gl.uniform4f(uM, hx * cv.width, (1 - hy) * cv.height, warp, cv.height);
    const t = reduce ? 0 : (now - t0) / 1000;
    gl.uniform1f(uT, t);
    gl.uniform3f(uCam, .16 * Math.sin(t * .05) + .16 * mx, 1.25 + .25 * Math.sin(t * .07) + .8 * my, -.21 + .03 * Math.sin(t * .09));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    // a slow GPU draws fewer pixels rather than a choppy hole
    if (last) { const ms = now - last; slow = ms > 22 && ms < 250 ? slow + 1 : Math.max(0, slow - 1); if (slow > 40 && q > .36) { q *= .7071; slow = 0; size(); } }
    last = now;
  }
  function frame(now) { draw(now); if (on && !reduce) requestAnimationFrame(frame); }
  size();
  addEventListener("resize", () => { size(); if (reduce) draw(performance.now()); });
  new IntersectionObserver(([e]) => { const was = on; on = e.isIntersecting; if (on && !was && !reduce) { last = 0; requestAnimationFrame(frame); } }).observe(cv);
  requestAnimationFrame((t) => { frame(t); cv.classList.add("on"); });
})();
