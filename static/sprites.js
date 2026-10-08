// Pixel sprites shared by the Office and Flows pages: Clawd plus Clawd Bot's bot shapes.
"use strict";
const BODY = "#D97757";
// Pages may define a global `theme` object (read from CSS variables); these are the fallbacks.
function spriteColor(name) {
  const fallback = { muted: "#8d93a8", waiting: "#e5566e" }[name];
  return (typeof theme !== "undefined" && theme[name]) || fallback;
}

// Clawd on a 12x8 grid, drawn at (x, y) with `c` pixels per cell.
function drawClawd(ctx, x, y, c, o) {
  const { state: st, t, tired = 0, body = BODY, look = 0, seed = 0 } = o;
  let bob = 0;
  if (st === "waiting") bob = Math.abs(Math.sin(t * 4)) * 0.5;
  else if (st === "celebrate") bob = Math.abs(Math.sin(t * 7)) * 2;
  else if (st === "sleeping") bob = Math.sin(t * 1.2) > 0.4 ? 0.2 : 0;
  const Y = y - bob * c;
  const px = (col, row, color, w = 1, h = 1) => {
    ctx.fillStyle = color;
    ctx.fillRect(Math.round(x + col * c), Math.round(Y + row * c), Math.ceil(w * c), Math.ceil(h * c));
  };
  px(2, 0, body, 8, 6);
  if (st === "working") {
    const f = Math.floor(t * 8 + seed) % 2 ? 0.5 : 0;
    px(0, 4.2 + f, body, 3, 1.4); px(9, 4.7 - f, body, 3, 1.4);
  } else {
    const up = st === "celebrate" || (st === "waiting" && Math.floor(t * 4) % 2 === 0);
    px(0, up ? 1 : 2, body, 12, 2);
  }
  for (const col of [2, 4, 7, 9]) px(col, 6, body, 1, 2);

  const tt = t + seed;
  const blink = st === "idle" && tt % 4.5 < 0.15;
  const wink = (st === "idle" || st === "working") && tired < 2 && tt % 6.5 < 0.4;
  const yawn = tired >= 2 && st === "idle" && tt % 22 < 1.6;
  const lid = [0, 0.2, 0.5, 0.76][tired];
  for (const col of [3, 8]) {
    if (st === "sleeping" || blink || yawn || (wink && col === 8)) {
      px(col, 1.45, "#000", 1, 0.2);
    } else if (st === "celebrate") {
      ctx.strokeStyle = "#000"; ctx.lineWidth = Math.max(1.5, c / 3); ctx.beginPath();
      ctx.moveTo(x + col * c, Y + 2 * c); ctx.lineTo(x + (col + 0.5) * c, Y + 1 * c);
      ctx.lineTo(x + (col + 1) * c, Y + 2 * c); ctx.stroke();
    } else {
      px(col + look * 0.3, 1, "#000");
      if (lid) px(col + look * 0.3 - 0.05, 0.95, body, 1.1, lid + 0.05);
    }
  }
  if (yawn) px(5, 3, "#000", 2, 1.4);
  if (tired === 3 && st !== "sleeping") {
    const sx = x + 9.5 * c + Math.sin(t * 2) * 2;
    ctx.fillStyle = "#7dcfff"; ctx.beginPath();
    ctx.moveTo(sx, Y - 1.4 * c); ctx.lineTo(sx - 0.5 * c, Y - 0.3 * c); ctx.lineTo(sx + 0.5 * c, Y - 0.3 * c);
    ctx.fill();
  }
  if (st === "sleeping") {
    ctx.fillStyle = spriteColor("muted"); ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    for (let i = 0; i < 3; i++) {
      const p = (t * 0.45 + i / 3) % 1;
      ctx.font = `bold ${Math.round(c * (1.4 + p * 1.2))}px system-ui`;
      ctx.fillText("z", x + 10.5 * c + p * 2.5 * c, Y - 0.2 * c - p * 4 * c);
    }
  }
}

// Clawd Bot's bots: each has its own pixel shape (# body, k darker accent, e eye).
const BOT_SHAPES = {
  crab:  ["..########..", "..#e####e#..", "############", "############", "..########..", "..########..", "..#.#..#.#..", "..#.#..#.#.."],
  scout: ["...#....#...", "....#..#....", "..########..", ".#e######e#.", ".##########.", "..########..", "...#.##.#...", "..##....##.."],
  byte:  [".....kk.....", "..########..", ".##e####e##.", ".##########.", "#.########.#", "#.########.#", "..##....##..", "..##....##.."],
  muse:  ["...######...", "..########..", ".##e####e##.", ".##########.", ".##########.", ".##########.", ".##########.", ".##.##.##.##"],
  golem: ["..########..", "..#e####e#..", "..########..", "############", "##.######.##", "kk.######.kk", "...##..##...", "..###..###.."],
  bug:   ["..k......k..", "...k....k...", "..########..", ".#e##kk##e#.", "#####kk#####", ".####kk####.", "#.########.#", "#..#....#..#"],
  guard: [".....kk.....", "...######...", "..########..", "..#kkkkkk#..", "..#e#kk#e#..", "..########..", "...######...", "..##....##.."],
  owl:   [".##......##.", ".###....###.", ".##########.", "##ee####ee##", "#####kk#####", ".##########.", "..########..", "...kk..kk..."],
  rocket:[".....##.....", "....####....", "...######...", "...#e##e#...", "...######...", "..########..", ".##.####.##.", "....k..k...."],
};
function drawBot(ctx, bot, x, y, c, o) {
  const { state = "idle", t = 0 } = o, rows = BOT_SHAPES[bot.shape] || BOT_SHAPES.crab;
  const n = parseInt(bot.color.slice(1), 16), mix = (m, p) => `rgb(${[n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(v + (m - v) * p)).join(",")})`;
  const dark = mix(0, 0.4), bob = state === "working" ? Math.abs(Math.sin(t * 6)) * 0.35 : state === "waiting" ? Math.abs(Math.sin(t * 4)) * 0.5 : 0;
  const closed = state === "sleeping" || t % 4.5 < 0.15, Y = y - bob * c;
  rows.forEach((row, ry) => [...row].forEach((ch, cx) => {
    if (ch === "." ) return;
    const left = Math.round(x + cx * c), size = Math.ceil(c);
    ctx.fillStyle = ch === "k" ? dark : bot.color; ctx.fillRect(left, Math.round(Y + ry * c), size, size);
    if (ch === "e") { ctx.fillStyle = "#000"; closed ? ctx.fillRect(left, Math.round(Y + (ry + 0.45) * c), size, Math.ceil(c * 0.2)) : ctx.fillRect(left + (state === "working" ? Math.round(c * 0.3) : 0), Math.round(Y + ry * c), size, size); }
  }));
  if (state === "working") for (let i = 0; i < 3; i++) {   // typing dots
    const on = Math.floor(t * 4) % 3 === i;
    ctx.fillStyle = on ? bot.color : mix(255, 0.55);
    ctx.fillRect(Math.round(x + (4.2 + i * 1.5) * c), Math.round(Y - 1.4 * c - (on ? c * 0.3 : 0)), Math.ceil(c * 0.9), Math.ceil(c * 0.9));
  }
  if (state === "waiting") { ctx.fillStyle = spriteColor("waiting"); ctx.font = `bold ${Math.round(c * 3)}px system-ui`; ctx.textAlign = "left"; ctx.fillText("!", x + 10.6 * c, Y + 1.5 * c); }
}

// Pixel icons for the non-agent nodes, in the same 12x8 style as the bots (# body, k darker accent).
const NODE_ICONS = {
  checkpoint: { color: "#7aa2f7", rows: ["############", ".##########.", "..########..", "...######...", "....####....", ".....kk.....", ".....kk.....", ".....kk....."] },
  approval:   { color: "#e0a23c", rows: ["...#.#.#....", "...#.#.#.#..", "...#.#.#.#..", ".#.#######..", ".#########..", "..########..", "...######...", "...kkkkkk..."] },
  done:       { color: "#e6b450", rows: [".##########.", "##.######.##", "#..######..#", ".#.######.#.", "...######...", ".....##.....", "....kkkk....", "...kkkkkk..."] },
};
function drawIcon(ctx, kind, x, y, c, o = {}) {
  const icon = NODE_ICONS[kind]; if (!icon) return;
  const { state = "idle", t = 0 } = o;
  const n = parseInt(icon.color.slice(1), 16), dark = `rgb(${[n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(v * 0.6)).join(",")})`;
  const bob = state === "working" || state === "waiting" ? Math.abs(Math.sin(t * 4)) * 0.4 : 0, Y = y - bob * c;
  icon.rows.forEach((row, ry) => [...row].forEach((ch, cx) => {
    if (ch === ".") return;
    ctx.fillStyle = ch === "k" ? dark : icon.color;
    ctx.fillRect(Math.round(x + cx * c), Math.round(Y + ry * c), Math.ceil(c), Math.ceil(c));
  }));
}
