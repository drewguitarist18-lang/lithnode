// Styled pop-ups for every HQ page, instead of the browser's grey boxes:
//   await ui.confirm({ title, text, ok, danger })  -> true / false
//   ui.menu(x, y, [{ label, icon, action, danger, disabled } | { sep: true }])
// Colors come from each page's own CSS variables, with fallbacks.
"use strict";
(function () {
  const css = `
  .ui-pop { --ui-bg: var(--pad, var(--panel, #171717)); --ui-line: var(--line, #262626); --ui-ink: var(--ink, #ededed);
            --ui-muted: var(--muted, #8d8d8d); --ui-danger: var(--failed, var(--err, #e5566e)); --ui-accent: var(--accent, #D97757);
            --ui-hover: var(--hover, color-mix(in srgb, var(--ui-ink) 8%, transparent));
            font: 13.5px/1.45 "Segoe UI", system-ui, sans-serif; color: var(--ui-ink); }
  dialog.ui-pop { border: 1px solid var(--ui-line); background: var(--ui-bg); border-radius: 16px; padding: 20px 20px 16px;
                  width: min(380px, 92vw); box-shadow: 0 24px 70px rgba(0, 0, 0, .45); }
  dialog.ui-pop[open] { animation: ui-in .14s ease-out; }
  dialog.ui-pop::backdrop { background: rgba(8, 9, 14, .5); backdrop-filter: blur(2px); }
  .ui-pop h3 { margin: 0 0 6px; font-size: 16px; font-weight: 650; text-transform: none; letter-spacing: normal; color: var(--ui-ink); }
  .ui-pop p { margin: 0; color: var(--ui-muted); }
  .ui-acts { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
  .ui-btn { font: inherit; cursor: pointer; border-radius: 9px; padding: 7px 14px; border: 1px solid var(--ui-line);
            background: transparent; color: var(--ui-ink); }
  .ui-btn:hover { background: var(--ui-hover); }
  .ui-btn.go { background: var(--ui-accent); border-color: var(--ui-accent); color: #fff; font-weight: 600; }
  .ui-btn.go.danger { background: var(--ui-danger); border-color: var(--ui-danger); }
  .ui-btn.go:hover { filter: brightness(1.08); }
  .ui-menu { position: fixed; z-index: 1000; min-width: 190px; padding: 5px; border-radius: 12px; border: 1px solid var(--ui-line);
             background: var(--ui-bg); box-shadow: 0 14px 40px rgba(0, 0, 0, .4); animation: ui-in .1s ease-out; }
  .ui-menu button { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; font: inherit; color: inherit;
                    background: none; border: 0; border-radius: 8px; padding: 7px 10px; cursor: pointer; }
  .ui-menu button:hover:not(:disabled), .ui-menu button:focus-visible { background: var(--ui-hover); outline: none; }
  .ui-menu button:disabled { opacity: .4; cursor: default; }
  .ui-menu button.danger { color: var(--ui-danger); }
  .ui-menu i { width: 16px; text-align: center; font-style: normal; color: var(--ui-muted); }
  .ui-menu button.danger i { color: inherit; }
  .ui-menu hr { border: 0; border-top: 1px solid var(--ui-line); margin: 4px 2px; }
  @keyframes ui-in { from { opacity: 0; transform: scale(.97); } }`;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function confirm({ title = "Are you sure?", text = "", ok = "OK", cancel = "Cancel", danger = false } = {}) {
    return new Promise((resolve) => {
      const d = document.createElement("dialog");
      d.className = "ui-pop";
      d.innerHTML = `<h3>${esc(title)}</h3>${text ? `<p>${esc(text)}</p>` : ""}
        <div class="ui-acts"><button class="ui-btn" value="no">${esc(cancel)}</button>
        <button class="ui-btn go${danger ? " danger" : ""}" value="yes">${esc(ok)}</button></div>`;
      document.body.appendChild(d);
      let answer = false;
      d.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (b) { answer = b.value === "yes"; d.close(); }
        else if (e.target === d) d.close();             // click on the dim backdrop = cancel
      });
      d.addEventListener("close", () => { d.remove(); resolve(answer); });
      d.showModal();
      d.querySelector(".go").focus();
    });
  }

  let open = null;
  function closeMenu() { if (open) { open.remove(); open = null; } }
  function menu(x, y, items) {
    closeMenu();
    const m = document.createElement("div");
    m.className = "ui-menu ui-pop";
    m.innerHTML = items.map((it, i) => it.sep ? "<hr>"
      : `<button data-i="${i}"${it.disabled ? " disabled" : ""} class="${it.danger ? "danger" : ""}"><i>${esc(it.icon || "")}</i>${esc(it.label)}</button>`).join("");
    document.body.appendChild(m);
    const r = m.getBoundingClientRect();   // keep it on screen
    m.style.left = Math.min(x, innerWidth - r.width - 6) + "px";
    m.style.top = Math.min(y, innerHeight - r.height - 6) + "px";
    m.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-i]");
      if (!b || b.disabled) return;
      closeMenu();
      items[+b.dataset.i].action();
    });
    m.addEventListener("contextmenu", (e) => e.preventDefault());
    open = m;
  }
  document.addEventListener("mousedown", (e) => { if (open && !open.contains(e.target)) closeMenu(); }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
  window.addEventListener("blur", closeMenu);
  window.addEventListener("wheel", closeMenu, { passive: true });

  window.ui = { confirm, menu, closeMenu };
})();
