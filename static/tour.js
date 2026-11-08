// The welcome tour: a few pop-ups that point at the parts of the Flows page, once on first launch.
//   tour.start(steps, done)   steps: [{ title, text, ok?, at? (CSS selectors to point at, the first on screen wins;
//                                       none = a card in the middle), color?, icon? (SVG inner markup, 24x24),
//                                       enter? (runs while the step shows; may return a clean-up function),
//                                       media? (HTML shown above the text, for enter() to animate), wide? (a bigger card) }]
// Esc or Skip ends it, Enter or → goes on, ← goes back. A step whose target isn't on screen is skipped.
// The spotlight glides from one target to the next with a soft ring in that step's color, and the card follows it.
"use strict";
(function () {
  const HUES = ["#8b7cff", "#4fa8ff", "#36d39a", "#ffb547", "#ff6b8b", "#47d7e0", "#c084fc", "#8b7cff"];
  const css = `
  .tour-catch { position: fixed; inset: 0; z-index: 1999; }
  .tour-dim { position: fixed; z-index: 2000; pointer-events: none; border-radius: 14px;
              box-shadow: 0 0 0 9999px rgba(6, 7, 12, .66), 0 0 0 2px var(--tc), 0 0 28px 4px color-mix(in srgb, var(--tc) 55%, transparent);
              transition: left .45s cubic-bezier(.2,.8,.2,1), top .45s cubic-bezier(.2,.8,.2,1), width .45s cubic-bezier(.2,.8,.2,1),
                          height .45s cubic-bezier(.2,.8,.2,1), border-radius .45s, box-shadow .45s, opacity .3s; }
  .tour-dim::after { content: ""; position: absolute; inset: -2px; border-radius: inherit; border: 2px solid var(--tc);
                     animation: tour-pulse 1.8s ease-out infinite; }
  .tour-dim.mid { border-radius: 24px; box-shadow: 0 0 0 9999px rgba(6, 7, 12, .66); }
  .tour-dim.mid::after { display: none; }
  @keyframes tour-pulse { from { opacity: .9; transform: scale(1); } to { opacity: 0; transform: scale(1.06); } }

  .tour-pop { position: fixed; z-index: 2001; width: min(340px, calc(100vw - 24px)); padding: 18px 18px 14px; box-sizing: border-box;
              border: 1px solid color-mix(in srgb, var(--tc) 35%, var(--line, #24242a)); border-radius: 16px;
              background: radial-gradient(120% 90% at 0% 0%, color-mix(in srgb, var(--tc) 16%, transparent), transparent 60%), var(--pad, #141417);
              color: var(--ink, #ecebe6); font: 13.5px/1.55 var(--sans, "Segoe UI"), system-ui, sans-serif;
              box-shadow: 0 30px 80px rgba(0, 0, 0, .5), 0 0 0 1px rgba(255, 255, 255, .03) inset;
              transition: left .45s cubic-bezier(.2,.8,.2,1), top .45s cubic-bezier(.2,.8,.2,1), border-color .45s;
              animation: tour-in .35s cubic-bezier(.2,.8,.2,1); }
  .tour-pop.hero { width: min(400px, calc(100vw - 24px)); padding: 26px 24px 16px; text-align: center; }
  .tour-pop.wide { width: min(600px, calc(100vw - 24px)); }
  .tour-pop .media { margin: 2px 0 14px; }
  @keyframes tour-in { from { opacity: 0; transform: translateY(8px) scale(.97); } to { opacity: 1; transform: none; } }
  .tour-pop .body { animation: tour-fade .3s ease; }
  @keyframes tour-fade { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .tour-pop .top { display: flex; align-items: center; gap: 11px; margin-bottom: 8px; }
  .tour-pop.hero .top { flex-direction: column; gap: 12px; margin-bottom: 10px; }
  .tour-pop .ic { flex: none; width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; color: #fff;
                  background: linear-gradient(140deg, var(--tc), color-mix(in srgb, var(--tc) 55%, #000));
                  box-shadow: 0 6px 18px color-mix(in srgb, var(--tc) 45%, transparent); }
  .tour-pop.hero .ic { width: 56px; height: 56px; border-radius: 16px; }
  .tour-pop .ic svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .tour-pop.hero .ic svg { width: 28px; height: 28px; }
  .tour-pop .n { font: 600 10.5px var(--mono, monospace); letter-spacing: .08em; text-transform: uppercase; color: var(--tc); }
  .tour-pop h3 { margin: 1px 0 0; font-size: 16.5px; font-weight: 680; letter-spacing: -.01em; }
  .tour-pop.hero h3 { font-size: 21px; }
  .tour-pop p { margin: 0; color: var(--muted, #a3a29c); }
  .tour-pop .bar { height: 3px; border-radius: 3px; background: var(--line, #24242a); margin: 16px 0 12px; overflow: hidden; }
  .tour-pop .bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, ${HUES[0]}, var(--tc));
                     transition: width .45s cubic-bezier(.2,.8,.2,1); }
  .tour-pop .acts { display: flex; align-items: center; gap: 8px; }
  .tour-pop button { font: inherit; cursor: pointer; border-radius: 10px; padding: 7px 14px; border: 1px solid var(--line, #24242a);
                     background: transparent; color: inherit; transition: background .15s, transform .1s, filter .15s; }
  .tour-pop button:hover { background: var(--hover, #1b1b1f); }
  .tour-pop button:active { transform: scale(.97); }
  .tour-pop button.skip { border-color: transparent; color: var(--muted, #a3a29c); margin-right: auto; padding-left: 4px; white-space: nowrap; }
  .tour-pop button.go { margin-left: auto; border: 0; font-weight: 650; color: #fff;
                        background: linear-gradient(140deg, var(--tc), color-mix(in srgb, var(--tc) 60%, #000));
                        box-shadow: 0 6px 18px color-mix(in srgb, var(--tc) 40%, transparent); }
  .tour-pop button.go:hover { filter: brightness(1.1); background: linear-gradient(140deg, var(--tc), color-mix(in srgb, var(--tc) 60%, #000)); }
  .tour-pop .skip + .go, .tour-pop .back + .go { margin-left: 0; }
  .tour-pop .tip { position: absolute; width: 12px; height: 12px; background: var(--pad, #141417); transform: rotate(45deg);
                   border: 1px solid color-mix(in srgb, var(--tc) 35%, var(--line, #24242a)); transition: left .45s, top .45s; }
  .tour-pop .tip.up { top: -7px; border-right: 0; border-bottom: 0; }
  .tour-pop .tip.down { bottom: -7px; border-left: 0; border-top: 0; }
  .tour-pop .tip.left { left: -7px; border-right: 0; border-top: 0; }
  .tour-pop .tip.right { right: -7px; border-left: 0; border-bottom: 0; }
  @media (prefers-reduced-motion: reduce) {
    .tour-dim, .tour-pop, .tour-pop .bar i, .tour-pop .tip { transition: none; }
    .tour-dim::after, .tour-pop, .tour-pop .body { animation: none; }
  }`;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4 && r.bottom > 0 && r.top < innerHeight ? r : null; };
  const spot = (sel) => { const el = [...document.querySelectorAll(sel)].find(shown); return el ? shown(el) : null; };   // the first one on screen
  const SPARK = '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>';

  function start(all, done = () => {}) {
    const steps = all.filter((s) => !s.at || spot(s.at));
    if (!steps.length) return;
    const catcher = Object.assign(document.createElement("div"), { className: "tour-catch" });
    const dim = Object.assign(document.createElement("div"), { className: "tour-dim mid" });
    const pop = Object.assign(document.createElement("div"), { className: "tour-pop" });
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-live", "polite");
    document.body.append(catcher, dim, pop);
    // the first frame: a spotlight that grows from the middle of the screen
    Object.assign(dim.style, { left: innerWidth / 2 + "px", top: innerHeight / 2 + "px", width: "0px", height: "0px" });
    let i = 0, leave = null;   // leave: the clean-up of a step's enter() (a typing demo, say)
    const color = (s, j) => s.color || HUES[j % HUES.length];

    function place() {
      const s = steps[i], r = s.at && spot(s.at), pad = 6;
      dim.classList.toggle("mid", !r);
      if (r) Object.assign(dim.style, { left: r.left - pad + "px", top: r.top - pad + "px", width: r.width + pad * 2 + "px", height: r.height + pad * 2 + "px" });
      else Object.assign(dim.style, { left: innerWidth / 2 + "px", top: innerHeight / 2 + "px", width: "0px", height: "0px" });
      const w = pop.offsetWidth, h = pop.offsetHeight, gap = 18, fit = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
      let x = (innerWidth - w) / 2, y = (innerHeight - h) / 2, side = "";
      if (r) {   // beside the target: below, above, right or left, whichever has room
        const cx = fit(r.left + r.width / 2 - w / 2, 12, innerWidth - w - 12), cy = fit(r.top + r.height / 2 - h / 2, 12, innerHeight - h - 12);
        if (innerHeight - r.bottom > h + gap + 12) [x, y, side] = [cx, r.bottom + gap, "up"];
        else if (r.top > h + gap + 12) [x, y, side] = [cx, r.top - h - gap, "down"];
        else if (innerWidth - r.right > w + gap + 12) [x, y, side] = [r.right + gap, cy, "left"];
        else if (r.left > w + gap + 12) [x, y, side] = [r.left - w - gap, cy, "right"];
        else [x, y] = [cx, innerHeight - h - 12];
      }
      Object.assign(pop.style, { left: x + "px", top: y + "px" });
      const tip = pop.querySelector(".tip");
      if (tip) {   // the little pointer on the card's edge, lined up with the target's middle
        tip.className = "tip " + side;
        tip.hidden = !side;
        if (side === "up" || side === "down") Object.assign(tip.style, { left: fit(r.left + r.width / 2 - x - 6, 18, w - 30) + "px", top: "" });
        else if (side) Object.assign(tip.style, { top: fit(r.top + r.height / 2 - y - 6, 18, h - 30) + "px", left: "" });
      }
    }
    function show() {
      if (leave) { leave(); leave = null; }
      const s = steps[i], last = i === steps.length - 1, hero = !s.at, c = color(s, i);
      pop.style.setProperty("--tc", c);
      dim.style.setProperty("--tc", c);
      pop.classList.toggle("hero", hero);
      pop.classList.toggle("wide", !!s.wide);
      pop.innerHTML = `<span class="tip" hidden></span><div class="body">
        <div class="top"><span class="ic"><svg viewBox="0 0 24 24">${s.icon || SPARK}</svg></span>
          <div><div class="n">${hero && i === 0 ? "Quick tour" : `Step ${i + 1} of ${steps.length}`}</div><h3>${esc(s.title)}</h3></div></div>
        ${s.media ? `<div class="media">${s.media}</div>` : ""}<p>${esc(s.text)}</p></div>
        <div class="bar"><i style="width:${((i + 1) / steps.length) * 100}%"></i></div>
        <div class="acts">${last ? "" : `<button class="skip" data-a="end">Skip</button>`}
          ${i ? `<button class="back" data-a="back">Back</button>` : ""}<button class="go" data-a="next">${esc(s.ok || (last ? "Let's go" : "Next"))}</button></div>`;
      requestAnimationFrame(place);   // after layout, so the card's size is known
      pop.querySelector(".go").focus({ preventScroll: true });
      if (s.enter) leave = s.enter() || null;
    }
    function end() {
      if (leave) { leave(); leave = null; }
      removeEventListener("resize", place); removeEventListener("keydown", key, true);
      pop.style.transition = dim.style.transition = "opacity .25s";
      pop.style.opacity = dim.style.opacity = "0";
      setTimeout(() => { catcher.remove(); dim.remove(); pop.remove(); }, 260);
      done();
    }
    const go = (d) => { i += d; if (i >= steps.length) return end(); i = Math.max(0, i); show(); };
    function key(e) {
      if (e.key === "Escape") { e.preventDefault(); end(); }
      else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
      else return;
      e.stopPropagation();
    }
    pop.addEventListener("click", (e) => { const a = e.target.closest("[data-a]")?.dataset.a; if (a === "end") end(); else if (a) go(a === "next" ? 1 : -1); });
    addEventListener("resize", place); addEventListener("keydown", key, true);
    show();
  }
  window.tour = { start };
})();
