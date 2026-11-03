// The welcome tour: a few pop-ups that point at the parts of the Flows page, once on first launch.
//   tour.start(steps, done)   steps: [{ title, text, ok?, at? (CSS selectors to point at, the first on screen wins; none = a card in the middle) }]
// Esc or Skip ends it, Enter or → goes on, ← goes back. A step whose target isn't on screen is skipped.
"use strict";
(function () {
  const css = `
  .tour-dim { position: fixed; z-index: 2000; border-radius: 12px; pointer-events: none;
              box-shadow: 0 0 0 9999px rgba(8, 9, 14, .62); }
  .tour-dim.mid { left: 0; top: 0; width: 100%; height: 100%; border-radius: 0; box-shadow: none; background: rgba(8, 9, 14, .62); }
  .tour-dim:not(.mid) { outline: 2px solid var(--ink, #ecebe6); outline-offset: 3px; }
  .tour-catch { position: fixed; inset: 0; z-index: 1999; }
  .tour-pop { position: fixed; z-index: 2001; width: min(320px, calc(100vw - 24px)); padding: 16px 16px 12px;
              border: 1px solid var(--line, #24242a); border-radius: 14px; background: var(--pad, #141417);
              color: var(--ink, #ecebe6); font: 13.5px/1.5 var(--sans, "Segoe UI"), system-ui, sans-serif;
              box-shadow: 0 24px 70px rgba(0, 0, 0, .45); }
  .tour-pop .n { font: 11px var(--mono, monospace); color: var(--muted, #a3a29c); letter-spacing: .04em; }
  .tour-pop h3 { margin: 4px 0 6px; font-size: 16px; font-weight: 650; }
  .tour-pop p { margin: 0; color: var(--muted, #a3a29c); }
  .tour-pop .acts { display: flex; align-items: center; gap: 8px; margin-top: 14px; }
  .tour-pop button { font: inherit; cursor: pointer; border-radius: 9px; padding: 6px 13px; border: 1px solid var(--line, #24242a);
                     background: transparent; color: inherit; }
  .tour-pop button:hover { background: var(--hover, #1b1b1f); }
  .tour-pop button.skip { border-color: transparent; color: var(--muted, #a3a29c); margin-right: auto; padding-left: 4px; white-space: nowrap; }
  .tour-pop button.go { background: var(--accent, #ecebe6); border-color: var(--accent, #ecebe6); color: var(--on-accent, #08080a); font-weight: 600; }
  .tour-pop button.go:hover { filter: brightness(1.08); }
  .tour-pop .dots { display: flex; gap: 4px; }
  .tour-pop .dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--line, #24242a); }
  .tour-pop .dots i.on { background: var(--ink, #ecebe6); }`;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4 && r.bottom > 0 && r.top < innerHeight ? r : null; };
  const spot = (sel) => { const el = [...document.querySelectorAll(sel)].find(shown); return el ? shown(el) : null; };   // the first one on screen

  function start(all, done = () => {}) {
    const steps = all.filter((s) => !s.at || spot(s.at));
    if (!steps.length) return;
    const catcher = Object.assign(document.createElement("div"), { className: "tour-catch" });
    const dim = Object.assign(document.createElement("div"), { className: "tour-dim mid" });
    const pop = Object.assign(document.createElement("div"), { className: "tour-pop" });
    pop.setAttribute("role", "dialog");
    document.body.append(catcher, dim, pop);
    let i = 0;

    function place() {
      const s = steps[i], r = s.at && spot(s.at);
      dim.classList.toggle("mid", !r);
      if (r) Object.assign(dim.style, { left: r.left - 4 + "px", top: r.top - 4 + "px", width: r.width + 8 + "px", height: r.height + 8 + "px" });
      else Object.assign(dim.style, { left: "", top: "", width: "", height: "" });
      const w = pop.offsetWidth, h = pop.offsetHeight, gap = 16, fit = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
      let x = (innerWidth - w) / 2, y = (innerHeight - h) / 2;
      if (r) {   // beside the target: below, above, right or left, whichever has room
        const cx = fit(r.left + r.width / 2 - w / 2, 12, innerWidth - w - 12), cy = fit(r.top + r.height / 2 - h / 2, 12, innerHeight - h - 12);
        if (innerHeight - r.bottom > h + gap + 12) [x, y] = [cx, r.bottom + gap];
        else if (r.top > h + gap + 12) [x, y] = [cx, r.top - h - gap];
        else if (innerWidth - r.right > w + gap + 12) [x, y] = [r.right + gap, cy];
        else if (r.left > w + gap + 12) [x, y] = [r.left - w - gap, cy];
        else [x, y] = [cx, innerHeight - h - 12];
      }
      Object.assign(pop.style, { left: x + "px", top: y + "px" });
    }
    function show() {
      const s = steps[i], last = i === steps.length - 1;
      pop.innerHTML = `<div class="n">${i + 1} of ${steps.length}</div><h3>${esc(s.title)}</h3><p>${esc(s.text)}</p>
        <div class="acts">${last ? "" : `<button class="skip" data-a="end">Skip tour</button>`}
          <div class="dots"${last ? ' style="margin-right:auto"' : ""}>${steps.map((_, j) => `<i class="${j === i ? "on" : ""}"></i>`).join("")}</div>
          ${i ? `<button data-a="back">Back</button>` : ""}<button class="go" data-a="next">${esc(s.ok || (last ? "Done" : "Next"))}</button></div>`;
      place();
      pop.querySelector(".go").focus();
    }
    function end() {
      removeEventListener("resize", place); removeEventListener("keydown", key, true);
      catcher.remove(); dim.remove(); pop.remove();
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
