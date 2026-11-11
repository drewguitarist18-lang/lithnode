// Styled pop-ups for every HQ page, instead of the browser's grey boxes:
//   await ui.confirm({ title, text, ok, danger })  -> true / false
//   ui.menu(x, y, [{ label, icon, action, danger, disabled, on, hint, title } | { sep: true } | { head: "Label" }])
//   icon: a character, or { svg: inner SVG markup (24x24, stroked), color } for a colored icon tile
// Colors come from each page's own CSS variables, with fallbacks.
"use strict";
(function () {
  const css = `
  .ui-pop { --ui-bg: var(--pad, var(--panel, #171717)); --ui-line: var(--line, #262626); --ui-ink: var(--ink, #ededed);
            --ui-muted: var(--muted, #8d8d8d); --ui-danger: var(--failed, var(--err, #e5566e)); --ui-accent: var(--accent, #D97757);
            --ui-hover: var(--hover, color-mix(in srgb, var(--ui-ink) 8%, transparent));
            font: 13.5px/1.45 var(--sans, "Segoe UI"), system-ui, sans-serif; color: var(--ui-ink); }
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
             background: var(--ui-bg); box-shadow: 0 14px 40px rgba(0, 0, 0, .4); animation: ui-in .1s ease-out;
             max-height: calc(100vh - 24px); overflow-y: auto; }
  .ui-menu button { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; font: inherit; color: inherit;
                    background: none; border: 0; border-radius: 8px; padding: 7px 10px; cursor: pointer; }
  .ui-menu button:hover:not(:disabled), .ui-menu button:focus-visible { background: var(--ui-hover); outline: none; }
  .ui-menu button:disabled { opacity: .4; cursor: default; }
  .ui-menu button.danger { color: var(--ui-danger); }
  .ui-menu i { width: 16px; text-align: center; font-style: normal; color: var(--ui-muted); }
  .ui-menu button.on i { color: var(--ui-ink); }
  .ui-menu small { margin-left: auto; padding-left: 14px; color: var(--ui-muted); font-size: 12px; }
  .ui-menu button.danger i { color: inherit; }
  .ui-menu i.ci { flex: none; width: 24px; height: 24px; margin: -2px 0; border-radius: 7px; display: grid; place-items: center;
                  color: var(--ic); background: color-mix(in srgb, var(--ic) 16%, transparent);
                  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ic) 22%, transparent); }
  .ui-menu i.ci svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .ui-menu button:hover:not(:disabled) i.ci { background: color-mix(in srgb, var(--ic) 26%, transparent); }
  .ui-menu hr { border: 0; border-top: 1px solid var(--ui-line); margin: 4px 2px; }
  .ui-menu { max-width: min(340px, calc(100vw - 12px)); max-height: calc(100vh - 12px); overflow-y: auto; }
  .ui-menu .l { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ui-mhead { padding: 6px 10px 3px; font-size: 11.5px; font-weight: 600; color: var(--ui-muted); }
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
        <div class="ui-acts">${cancel ? `<button class="ui-btn" value="no">${esc(cancel)}</button>` : ""}
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
  const ico = (c) => c && c.svg ? `<i class="ci" style="--ic:${esc(c.color || "currentColor")}"><svg viewBox="0 0 24 24" aria-hidden="true">${c.svg}</svg></i>` : `<i>${esc(c || "")}</i>`;
  function closeMenu() { if (open) { open.remove(); open = null; } }
  function menu(x, y, items) {
    closeMenu();
    const m = document.createElement("div");
    m.className = "ui-menu ui-pop";
    m.innerHTML = items.map((it, i) => it.sep ? "<hr>" : it.head ? `<div class="ui-mhead">${esc(it.head)}</div>`
      : `<button data-i="${i}"${it.disabled ? " disabled" : ""} class="${it.danger ? "danger" : ""}${it.on ? " on" : ""}"${it.title ? ` title="${esc(it.title)}"` : ""}>${ico(it.icon)}<span class="l">${esc(it.label)}</span>${it.hint ? `<small>${esc(it.hint)}</small>` : ""}</button>`).join("");
    document.body.appendChild(m);
    const r = m.getBoundingClientRect();   // keep it on screen
    m.style.left = Math.max(6, Math.min(x, innerWidth - r.width - 6)) + "px";
    m.style.top = Math.max(6, Math.min(y, innerHeight - r.height - 6)) + "px";
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
  window.addEventListener("wheel", (e) => { if (open && !open.contains(e.target)) closeMenu(); }, { passive: true });

  // colored menu icons, shared by every page: ui.icon(name, color?) -> { svg, color } for ui.menu items
  const MI = {
    team: ['<circle cx="9" cy="8.5" r="3"/><circle cx="17" cy="9.5" r="2.3"/><path d="M3.5 19c.6-3 2.8-4.5 5.5-4.5s4.9 1.5 5.5 4.5M15 14.6c2.5-.3 4.6 1 5.2 3.9"/>', "#D97757"],
    merge: ['<circle cx="6" cy="6" r="2.2"/><circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="12" r="2.2"/><path d="M6 8.2v7.6M8 6.6c5 .5 7.6 2.4 8 4M8 17.4c5-.5 7.6-2.4 8-4"/>', "#7aa2f7"],
    hand: ['<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12M11 11V4.5a1.5 1.5 0 0 1 3 0V12M14 11.5V6a1.5 1.5 0 0 1 3 0v8a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-2.7L3.5 13a1.6 1.6 0 0 1 2.6-1.8L8 13"/>', "#e0a23c"],
    flag: ['<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>', "#e6b450"],
    fit: ['<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>', "#47d7e0"],
    unplug: ['<path d="M9 7.5 6.5 5M17 15.5l2.5 2.5M10.5 13.5l-2 2M13.5 10.5l2-2"/><path d="M8.5 11 6 13.5a3.5 3.5 0 0 0 5 5l2.5-2.5zM15.5 13 18 10.5a3.5 3.5 0 0 0-5-5L10.5 8z"/>', "#ffb547"],
    dot: ['<circle cx="12" cy="12" r="4.5" fill="currentColor"/>', "#8b7cff"],
    plus: ['<path d="M12 5v14M5 12h14"/>', "#36d39a"],
    tpl: ['<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>', "#4fa8ff"],
    copy: ['<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>', "#8b7cff"],
    imp: ['<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M4.5 15.5v3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-3"/>', "#47d7e0"],
    exp: ['<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M4.5 15.5v3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-3"/>', "#ffb547"],
    trash: ['<path d="M4.5 7h15M10 11v6M14 11v6M6.5 7l1 12a1.5 1.5 0 0 0 1.5 1.5h6a1.5 1.5 0 0 0 1.5-1.5l1-12M9.5 7V4.5h5V7"/>', "#ff6b8b"],
    undo: ['<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>', "#7aa2f7"],
    redo: ['<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>', "#7aa2f7"],
    pen: ['<path d="M4.5 19.5 5.5 15 15.8 4.7a2 2 0 0 1 2.8 0l.7.7a2 2 0 0 1 0 2.8L9 18.5z"/><path d="M14 6.5l3.5 3.5"/>', "#4fa8ff"],
    tidyTb: ['<rect x="7" y="3.5" width="10" height="5" rx="1.5"/><rect x="7" y="15.5" width="10" height="5" rx="1.5"/><path d="M12 8.5v7"/>', "#36d39a"],
    tidyLr: ['<rect x="3.5" y="7" width="5" height="10" rx="1.5"/><rect x="15.5" y="7" width="5" height="10" rx="1.5"/><path d="M8.5 12h7"/>', "#36d39a"],
    gear: ['<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>', "#9aa6c4"],
    update: ['<path d="M20 11.5A8 8 0 0 0 5.6 7M4 12.5A8 8 0 0 0 18.4 17"/><path d="M5 3.5V7.5h4M19 20.5v-4h-4"/>', "#36d39a"],
    tour: ['<circle cx="12" cy="12" r="8.5"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>', "#c084fc"],
    web: ['<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.5 5.2 3.5 8.5s-1.1 6.1-3.5 8.5c-2.4-2.4-3.5-5.2-3.5-8.5S9.6 5.9 12 3.5z"/>', "#4fa8ff"],
    bug: ['<rect x="7.5" y="8" width="9" height="12" rx="4.5"/><path d="M9.5 8V6.5a2.5 2.5 0 0 1 5 0V8M4 13h3.5M16.5 13H20M5 8.5l2.8 1.8M19 8.5l-2.8 1.8M5 18.5l2.8-1.8M19 18.5l-2.8-1.8M12 11v9"/>', "#ff8a65"],
    palette: ['<path d="M12 3.5a8.5 8.5 0 0 0 0 17c1.3 0 1.9-.9 1.6-2-.3-1.2.4-2.3 1.7-2.3H17a3.5 3.5 0 0 0 3.5-3.5c0-5.1-3.8-9.2-8.5-9.2z"/><circle cx="7.8" cy="11" r="1.1" fill="currentColor"/><circle cx="10.5" cy="7.3" r="1.1" fill="currentColor"/><circle cx="15" cy="7.8" r="1.1" fill="currentColor"/>', "#c084fc"],
    bolt: ['<path d="M13 3 5 13.5h6L10 21l8-10.5h-6z"/>', "#ffb547"],
    folder: ['<path d="M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4.2l2 2.2H19a1.5 1.5 0 0 1 1.5 1.5v8.3a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5z"/>', "#47d7e0"],
    bell: ['<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2H4.5z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>', "#ffb547"],
    chart: ['<path d="M4 20h16"/><path d="M7 16v-4M12 16V7M17 16v-6"/>', "#36d39a"],
    kbd: ['<rect x="3" y="6.5" width="18" height="11" rx="2"/><path d="M7 10h.01M10 10h.01M13 10h.01M16 10h.01M8 14h8"/>', "#4fa8ff"],
    info: ['<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8h.01"/>', "#8b7cff"],
    code: ['<path d="m8.5 7-5 5 5 5M15.5 7l5 5-5 5"/>', "#c084fc"],
    key: ['<circle cx="8" cy="12" r="3.5"/><path d="M11.5 12H20M17 12v3M20 12v2.5"/>', "#ff6b8b"],
    plug: ['<path d="M9 3.5v4M15 3.5v4"/><path d="M6.5 7.5h11v3a5.5 5.5 0 0 1-11 0z"/><path d="M12 16v4.5"/>', "#D97757"],
    quit: ['<path d="M12 3.5v8"/><path d="M7 6.3a7.5 7.5 0 1 0 10 0"/>', "#ff6b8b"],
  };
  const icon = (k, color) => MI[k] ? { svg: MI[k][0], color: color || MI[k][1] } : "";
  window.ui = { confirm, menu, closeMenu, icon };
})();
