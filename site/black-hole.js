// The black hole behind the hero, ray traced live. Every pixel's light is bent around the hole (Schwarzschild), so the
// shadow, the far side of the disk lensed up over the top and down under the bottom, and the brighter side that comes
// toward you all fall out of the physics. The disk is a thin glowing slab, hot and bright inside, cold and smoky at its
// rim; its gas streams round in fine lanes, inner ones faster. The camera drifts slowly round and eases toward the
// cursor. No WebGL: the poster stays.
(() => {
  const cv = document.getElementById("hole");
  if (!cv) return;
  const gl = cv.getContext("webgl", { antialias: false, alpha: false, depth: false, powerPreference: "high-performance" });
  if (!gl) { cv.parentNode.classList.add("still"); return; }
  const D = 26;   // the camera's distance, in Schwarzschild radii
  const FS = `
    precision highp float;
    uniform vec2 uC; uniform float uK, uP, uN, uT; uniform vec3 uCam;
    const float D = ${D}., RIN = 1.6, ROUT = 14.5, BC = 2.598;
    float hash3(vec3 p){ p = fract(p * .3183099 + .1); p *= 17.; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
    float noise3(vec3 x){ vec3 i = floor(x), f = fract(x); f = f * f * (3. - 2. * f);
      return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x), mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
                 mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x), mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z); }
    float erf1(float x){ float t = x * x; return sign(x) * sqrt(1. - exp(-t * (1.2732 + .147 * t) / (1. + .147 * t))); }
    // the stars: a jittered grid on the six faces of a cube round the camera, at most one star a cell, each drawn round
    // on the sky and never smaller than a pixel. The grid is sized to the screen (uN), so any screen gets the same field
    float stars(vec3 d){
      vec3 a = abs(d);
      float m = max(a.x, max(a.y, a.z)), c = 0.;
      bool fx = a.x == m, fy = !fx && a.y == m;
      vec2 uv = (fx ? d.yz : fy ? d.xz : d.xy) / m;
      float face = fx ? step(0., d.x) : fy ? 2. + step(0., d.y) : 4. + step(0., d.z);
      for (int L = 0; L < 2; L++) {
        float N = L == 0 ? uN : uN * .45;
        vec2 id = floor((uv * .5 + .5) * N);
        vec3 k = vec3(id, face * 7.31 + float(L) * 31.7);
        if (hash3(k) < (L == 0 ? .95 : .7)) {
          vec2 su = (id + .2 + .6 * vec2(hash3(k + 3.1), hash3(k + 5.7))) / N * 2. - 1.;
          vec3 s = normalize(fx ? vec3(sign(d.x), su) : fy ? vec3(su.x, sign(d.y), su.y) : vec3(su, sign(d.z)));
          float b = hash3(k + 9.2), r = length(d - s);
          float sz = L == 0 ? .45 + .35 * b : .65 + 1.1 * b * b, R = max(uK * .6, uP * sz);
          c += (L == 0 ? .35 + 1.3 * b * b : .6 + 2.4 * b * b * b) * exp(-r * r / (R * R)) * min(1., uP * uP * sz * sz / (R * R));
        }
      }
      return c;
    }
    // the gas: lanes along the orbit, spaced by log radius. The finer ones fade out where a pixel spans them (blur),
    // so the disk seen edge on is a smooth band and seen through the lens a fan of fine rings
    float lanes(float lr, float a, float blur){
      vec2 cs = vec2(cos(a), sin(a));
      float s = (noise3(vec3(lr * 7., cs * 1.3)) - .5) * .9;
      s += (noise3(vec3(lr * 24., cs * 1.7 + 3.)) - .5) * .8 * smoothstep(.05, .018, blur);
      s += (noise3(vec3(lr * 70., cs * 2.3 + 7.)) - .5) * .6 * smoothstep(.016, .006, blur);
      return s;
    }
    // two copies of the lanes, each sheared by the orbit for one period and faded out as the other fades in, so the
    // gas streams for ever without winding up into noise
    float gas(float pr, float a, float blur){
      float w = .7071 * pow(pr, -1.5) * 1.6, P = 10.;
      float p1 = fract(uT / P), p2 = fract(uT / P + .5), k = 1. - abs(2. * p1 - 1.), lr = log(pr);
      float s = mix(lanes(lr, a - w * (p2 - .5) * P + 2.1, blur), lanes(lr, a - w * (p1 - .5) * P, blur), k);
      return clamp(.55 + s / sqrt(k * k + (1. - k) * (1. - k)), 0., 1.);   // two blended copies lose contrast: give it back
    }
    void main(){
      vec2 q = (gl_FragCoord.xy - uC) * uK;
      float cr = cos(uCam.z), sr = sin(uCam.z);
      q = vec2(cr * q.x - sr * q.y, sr * q.x + cr * q.y);
      float ca = cos(uCam.x), sa = sin(uCam.x), ce = cos(uCam.y), se = sin(uCam.y);
      vec3 pos = D * vec3(ce * sa, se, -ce * ca), fw = -pos / D, rt = vec3(ca, 0., sa), up = cross(fw, rt);
      vec3 v0 = normalize(fw + q.x * rt + q.y * up), vel = v0, am = cross(pos, vel);
      float h2 = dot(am, am), col = 0., T = 1., trav = 0.;
      bool fell = false;
      for (int i = 0; i < 240; i++) {
        float r2 = dot(pos, pos), r = sqrt(r2);
        if (r < 1.) { fell = true; break; }
        float dt = .08 * r2 / (r + 2.);
        vec3 p0 = pos;
        vel -= 1.5 * h2 * pos / (r2 * r2 * r) * dt;
        pos += vel * dt;
        float L = length(pos - p0), y0 = p0.y, y1 = pos.y, rc = length(p0.xz + pos.xz) * .5;
        trav += L;
        // the disk: a slab, Gaussian in height, that glows and absorbs. Each step takes the gas it passes through
        // exactly for the straight step (erf), looked up where the step comes nearest the middle of the slab
        if (rc > RIN - .3 && rc < ROUT + 1.) {
          float hb = .05 + .022 * rc;
          if (y0 * y1 < 0. || min(abs(y0), abs(y1)) < 3. * hb) {
            float s = y0 * y1 < 0. ? y0 / (y0 - y1) : step(abs(y1), abs(y0));
            vec3 pc = mix(p0, pos, s), d = (pos - p0) / L;
            float pr = length(pc.xz), a = atan(pc.z, pc.x), vy = max(abs(d.y), .02);
            float blur = (uK * trav / vy + min(L, 2. * hb / vy) * abs(dot(d.xz, pc.xz)) / pr) / pr;
            float tx = gas(pr, a, blur);
            float hh = hb * (.7 + .6 * tx);   // the slab puffs up with the gas: its edge is wispy
            float dy = (y1 - y0) / hh;
            float cd = (abs(dy) > .02 ? .8862 * (erf1(y1 / hh) - erf1(y0 / hh)) / dy : exp(-pow(.5 * (y0 + y1) / hh, 2.))) * L / hh;
            // thick inside, thinning outward: seen edge on, the outer gas still glows; seen through the lens, it fades
            float den = smoothstep(RIN, RIN + .35, pr) * smoothstep(ROUT, ROUT - 2., pr) * pow(2. / pr, 1.9) * (.3 + .9 * tx);
            float tau = cd * den;
            float b = sqrt(.5 / pr), dop = sqrt(1. - b * b) / (1. - b * dot(vec3(-pc.z, 0., pc.x) / pr, -d));   // gas coming toward you is brighter
            float S = 3.3 * pow(2. / pr, .85) * smoothstep(15.5, 8., pr) * (.45 + .9 * tx * tx) * pow(dop, 3.);
            float dT = exp(-tau);
            col += T * S * (1. - dT);
            T *= dT;
            if (T < .02) break;
          }
        }
        if (r > D + 6. && dot(pos, vel) > 0.) break;
      }
      // the photon ring: light that circles the hole before it gets out, piled up in a thin line at the shadow's edge
      float bi = sqrt(h2), pw = uK * D, ql = length(q) + 1e-6;
      col += T * exp(-pow((bi - BC * 1.004) / (1.4 * pw), 2.)) * (.75 - .45 * q.x / ql);
      // the stars, bent only part way: round far out, drawn into short arcs near the ring
      if (!fell) {
        vec3 vf = normalize(vel);
        float cdv = clamp(dot(v0, vf), -1., 1.), dl = acos(cdv) * .2;
        vec3 w = vf - v0 * cdv;
        float wl = length(w);
        col += T * stars(wl > 1e-5 ? v0 * cos(dl) + w / wl * sin(dl) : v0);
      }
      gl_FragColor = vec4((1. - exp(-col)) * vec3(.87, .885, .91), 1.);   // a cool silver, never quite white
    }`;
  const VS = "attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }";
  const sh = (t, src) => { const o = gl.createShader(t); gl.shaderSource(o, src); gl.compileShader(o); if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw gl.getShaderInfoLog(o); return o; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer()); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = (n) => gl.getUniformLocation(pr, n), uC = U("uC"), uK = U("uK"), uP = U("uP"), uN = U("uN"), uT = U("uT"), uCam = U("uCam");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const TS = Math.tan(Math.asin(3 * Math.sqrt(3) / 2 / D * Math.sqrt(1 - 1 / D)));   // the shadow's radius, as the tangent of its angle

  // the frame: at most 1.3 million pixels, and a slow GPU steps down from there. Wider than a phone, the hole's size
  // follows the width and its middle sits 37% down below the 44px bar; on a phone it follows the height and sits higher
  let q = 1;
  function size() {
    const r = cv.getBoundingClientRect(), w = r.width || 1, h = r.height || 1;
    const s = Math.min(devicePixelRatio || 1, Math.sqrt(1.3e6 / (w * h))) * q;
    const W = Math.max(1, Math.round(w * s)), H = Math.max(1, Math.round(h * s));
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    gl.viewport(0, 0, W, H);
    const phone = w < 640, hw = phone ? .105 * h : .152 * w;
    gl.uniform2f(uC, W / 2, H - (44 + (phone ? .255 : .37) * h) * s);
    gl.uniform1f(uK, TS / (hw * s));
    gl.uniform1f(uP, TS / hw);
    gl.uniform1f(uN, hw / (11 * TS));   // star cells about 22px across
  }
  // the camera eases toward the cursor: up lays the disk flat, nearly edge-on; down tips it toward you. Left and right
  // roll it a little. With no cursor (a phone) it rests in the middle
  let tx = 0, ty = 0, mx = 0, my = 0;
  if (!reduce) addEventListener("pointermove", (e) => { if (e.pointerType !== "touch") { tx = e.clientX / innerWidth * 2 - 1; ty = e.clientY / innerHeight * 2 - 1; } }, { passive: true });
  const deg = Math.PI / 180, t0 = performance.now();
  let on = true, last = 0, slow = 0;
  function draw(now) {
    const dt = last ? Math.min(.1, (now - last) / 1000) : 0, e = 1 - Math.exp(-dt * 1.3);
    mx += (tx - mx) * e; my += (ty - my) * e;
    const t = reduce ? 0 : (now - t0) / 1000;
    gl.uniform1f(uT, t + 40);
    gl.uniform3f(uCam, -.0025 * t, (5.5 + 4.5 * my) * deg, (11.5 - 2.2 * mx + 1.5 * my) * deg);
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
