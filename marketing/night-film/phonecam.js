// The phone's camera, shared by phone.html (the desk at night) and gym.html (the gym): the frame and its two lenses, the WebGL
// plumbing, the phone's processing (glare, vignette, tone curve, sharpening, noise) and TikTok's text over a photo.
const W = 1080, H = 1920;
const FOCAL = 540 / Math.tan(11.5 * Math.PI / 180);   // the 2x camera: 23 degrees across the portrait frame
const WIDE = 540 / Math.tan(21 * Math.PI / 180);      // the main camera: 42 degrees

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, k) => a + (b - a) * k;
const smooth = (k) => k * k * (3 - 2 * k);
const add = (a, b) => a.map((v, i) => v + b[i]), sub = (a, b) => a.map((v, i) => v - b[i]), mul = (a, k) => a.map((v) => v * k);
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => mul(a, 1 / Math.hypot(...a));
function mulberry(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

const VS = `#version 300 es
void main() { gl_Position = vec4(gl_VertexID == 1 ? 3.0 : -1.0, gl_VertexID == 2 ? 3.0 : -1.0, 0.0, 1.0); }`;

// the phone's processing: glare, vignette, tone curve, sharpening, noise
const POST = `#version 300 es
precision highp float;
out vec4 fragColor;
uniform sampler2D uImg;
uniform vec2 uRes;
uniform float uExpo, uSeed, uGrain;
float hash(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
vec3 tone(vec3 x) { x *= uExpo; return x * (1.0 + x / 5.0) / (1.0 + x); }
vec3 srgb(vec3 x) { x = clamp(x, 0.0, 1.0); return mix(x * 12.92, 1.055 * pow(x, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, x)); }
vec3 mip(int lod, vec2 uv) {   // a small mip through a cubic B-spline in four bilinear taps, so a wide glow doesn't show the mip's blocks
  vec2 size = vec2(textureSize(uImg, lod)), t = uv * size - 0.5, i = floor(t), f = t - i;
  vec2 w0 = (1.0 - f) * (1.0 - f) * (1.0 - f) / 6.0, w1 = (3.0 * f * f * f - 6.0 * f * f + 4.0) / 6.0, w3 = f * f * f / 6.0;
  vec2 g0 = w0 + w1, g1 = 1.0 - g0, c0 = (i - 0.5 + w1 / g0) / size, c1 = (i + 1.5 + w3 / g1) / size;
  float l = float(lod);
  return (textureLod(uImg, c0, l).rgb * g0.x + textureLod(uImg, vec2(c1.x, c0.y), l).rgb * g1.x) * g0.y
       + (textureLod(uImg, vec2(c0.x, c1.y), l).rgb * g0.x + textureLod(uImg, c1, l).rgb * g1.x) * g1.y;
}
void main() {
  vec2 uv = gl_FragCoord.xy / uRes, px = 1.0 / uRes, cc = uv - 0.5;
  vec3 c = vec3(texture(uImg, 0.5 + cc * 1.0008).r, texture(uImg, uv).g, texture(uImg, 0.5 + cc * 0.9992).b);
  vec3 b = (texture(uImg, uv + vec2(px.x * 1.4, 0.0)).rgb + texture(uImg, uv - vec2(px.x * 1.4, 0.0)).rgb
          + texture(uImg, uv + vec2(0.0, px.y * 1.4)).rgb + texture(uImg, uv - vec2(0.0, px.y * 1.4)).rgb) * 0.25;
  vec3 glare = mip(3, uv) * 0.45 + (mip(4, uv) + mip(5, uv)) * 0.175 + mip(6, uv) * 0.3 + (mip(7, uv) + mip(8, uv)) * 0.125;
  c += glare * 0.05; b += glare * 0.05;
  vec2 q = cc * vec2(1.0, 1.75);
  float vig = 1.0 - 0.3 * dot(q, q);
  vec3 o = srgb(tone(c * vig)), ob = srgb(tone(b * vig));
  o += (o - ob) * 0.65;   // the phone's sharpening, halos and all
  o = mix(o, o * o * (3.0 - 2.0 * o), 0.12);
  vec2 g = gl_FragCoord.xy / 2.3, i = floor(g), f = fract(g); f = f * f * (3.0 - 2.0 * f);
  float s = uSeed * 7.31;
  float n = mix(mix(hash(i + s), hash(i + vec2(1.0, 0.0) + s), f.x), mix(hash(i + vec2(0.0, 1.0) + s), hash(i + vec2(1.0, 1.0) + s), f.x), f.y) - 0.5;
  float n2 = hash(gl_FragCoord.xy + s * 1.7) - 0.5;
  float lum = dot(o, vec3(0.299, 0.587, 0.114));
  o += (n * 0.034 + n2 * 0.014) * uGrain * (0.3 + 0.7 * (1.0 - lum)) * vec3(0.98, 1.0, 1.06);
  fragColor = vec4(clamp(o, 0.0, 1.0), 1.0);
}`;

function compile(gl, fs) {   // a program and its uniforms by name
  const p = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, VS], [gl.FRAGMENT_SHADER, fs]]) {
    const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    gl.attachShader(p, s);
  }
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {}; const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) { const name = gl.getActiveUniform(p, i).name.replace(/\[0\]$/, ""); u[name] = gl.getUniformLocation(p, name); }
  return { p, u };
}
function texture(gl, format, w, h) {   // mipmapped, clamped
  const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texStorage2D(gl.TEXTURE_2D, Math.floor(Math.log2(Math.max(w, h))) + 1, format, w, h);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  return t;
}
// the light the sensor caught (a float texture) to the picture on the canvas, through the phone's processing
function develop(gl, post, hdr, { expo, seed, grain }) {
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, hdr); gl.generateMipmap(gl.TEXTURE_2D);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, W, H);
  gl.useProgram(post.p);
  gl.uniform1i(post.u.uImg, 1); gl.uniform2f(post.u.uRes, W, H); gl.uniform1f(post.u.uExpo, expo); gl.uniform1f(post.u.uSeed, seed);
  gl.uniform1f(post.u.uGrain, grain);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.finish();
}

// TikTok's own text over a photo: its font, white with a thick black rim, centred under the app's top bar and clear of its buttons.
// Each line is broken as evenly as it will go, the way you'd break it by hand.
function caption(g, say, big = 62) {
  g.textAlign = "center"; g.lineJoin = "round";
  let y = 300;
  say.forEach((s, k) => {
    const size = Math.round(k ? big * .74 : big);
    g.font = `600 ${size}px "TikTok Sans"`;
    const wrap = (max) => s.split(" ").reduce((ls, w) => {
      const l = ls.at(-1), tl = l ? l + " " + w : w;
      if (l && g.measureText(tl).width > max) ls.push(w); else ls[ls.length - 1] = tl;
      return ls;
    }, [""]);
    let lines = wrap(820);
    for (let max = 800; max > 300; max -= 20) { const l = wrap(max); if (l.length > lines.length) break; lines = l; }
    for (const l of lines) {
      y += size * 1.22;
      g.lineWidth = size * .16; g.strokeStyle = "#000"; g.strokeText(l, 540, y);
      g.fillStyle = "#fff"; g.fillText(l, 540, y);
    }
    y += size * .3;
  });
}
async function slide(cv, say, size) {   // the photo on the canvas with its text, as a JPEG in base64
  await document.fonts.load('600 62px "TikTok Sans"');
  const o = document.createElement("canvas"); o.width = W; o.height = H;
  const g = o.getContext("2d"); g.drawImage(cv, 0, 0);
  caption(g, say, size);
  return o.toDataURL("image/jpeg", .94).split(",")[1];
}
