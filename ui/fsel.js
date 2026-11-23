/* Menus déroulants maison : les listes natives de Windows (<select>) ne s'affichent pas dans les enregistrements
   vidéo (OBS, barre de jeu…). Chaque <select> reste dans la page (valeur, événements « change ») mais est caché,
   et un bouton + une liste dessinés en HTML le remplacent à l'écran. */
(function () {
  const css = `
  .fsel{position:relative;display:inline-flex;align-items:center;gap:8px;max-width:100%;cursor:pointer;user-select:none;
    font:inherit;font-size:13px;color:var(--text,#E8EDF5);background:var(--bg,#06070B);border:1px solid var(--line2,#1E2A38);
    border-radius:8px;padding:6px 26px 6px 8px;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:left}
  .fsel.flat{border-color:transparent;background:transparent;padding:2px 22px 2px 4px}
  .fsel:after{content:"";position:absolute;right:9px;top:50%;width:6px;height:6px;margin-top:-5px;border-right:2px solid currentColor;
    border-bottom:2px solid currentColor;transform:rotate(45deg);opacity:.7}
  .fsel:focus{outline:1px solid rgba(var(--accent-rgb,0,229,255),.7);outline-offset:1px}
  .fsel[aria-disabled=true]{opacity:.5;cursor:default}
  .fsel-list{position:fixed;z-index:99999;max-height:320px;overflow-y:auto;background:var(--panel,#0B0F16);
    border:1px solid rgba(var(--accent-rgb,0,229,255),.45);border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,.6);padding:4px;
    font-size:13px;color:var(--text,#E8EDF5)}
  .fsel-opt{padding:7px 10px;border-radius:6px;cursor:pointer;white-space:nowrap}
  .fsel-opt:hover,.fsel-opt.on{background:rgba(var(--accent-rgb,0,229,255),.14)}
  .fsel-opt.sel{color:var(--accent,#00E5FF)}
  .fsel-opt.dis{opacity:.4;cursor:default}
  .fsel-hidden{position:absolute!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important}`;
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  let open = null;   // { sel, btn, list, idx }

  function label(sel) {
    const o = sel.options[sel.selectedIndex];
    return o ? o.textContent : "";
  }

  function close() {
    if (!open) return;
    open.list.remove(); open.btn.setAttribute("aria-expanded", "false");
    open = null;
  }

  function choose(sel, i) {
    if (i < 0 || i >= sel.options.length || sel.options[i].disabled) return;
    if (sel.selectedIndex !== i) {
      sel.selectedIndex = i;
      sel.dispatchEvent(new Event("input", { bubbles: true }));
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }
    sync(sel);
  }

  function show(sel, btn) {
    close();
    if (sel.disabled) return;
    const list = document.createElement("div");
    list.className = "fsel-list"; list.setAttribute("role", "listbox");
    [...sel.options].forEach((o, i) => {
      const d = document.createElement("div");
      d.className = "fsel-opt" + (i === sel.selectedIndex ? " sel on" : "") + (o.disabled ? " dis" : "");
      d.textContent = o.textContent; d.setAttribute("role", "option");
      d.addEventListener("mousedown", e => { e.preventDefault(); choose(sel, i); close(); btn.focus(); });
      list.appendChild(d);
    });
    document.body.appendChild(list);
    const r = btn.getBoundingClientRect();
    list.style.minWidth = Math.max(r.width, 140) + "px";
    const h = list.offsetHeight, below = innerHeight - r.bottom - 8;
    list.style.left = Math.min(r.left, innerWidth - list.offsetWidth - 8) + "px";
    list.style.top = (h > below && r.top > below ? Math.max(8, r.top - h - 4) : r.bottom + 4) + "px";
    btn.setAttribute("aria-expanded", "true");
    open = { sel, btn, list, idx: sel.selectedIndex };
    const cur = list.children[sel.selectedIndex]; if (cur) cur.scrollIntoView({ block: "nearest" });
  }

  function move(d) {
    if (!open) return;
    const n = open.sel.options.length; let i = open.idx;
    for (let k = 0; k < n; k++) { i = (i + d + n) % n; if (!open.sel.options[i].disabled) break; }
    open.idx = i;
    [...open.list.children].forEach((c, j) => c.classList.toggle("on", j === i));
    open.list.children[i].scrollIntoView({ block: "nearest" });
  }

  function sync(sel) {
    const btn = sel._fsel; if (!btn) return;
    const t = label(sel);
    if (btn.textContent !== t) btn.textContent = t;
    btn.setAttribute("aria-disabled", sel.disabled ? "true" : "false");
    btn.style.display = sel.style.display === "none" || sel.hidden ? "none" : "";
    btn.title = sel.title || "";
  }

  function enhance(sel) {
    if (sel._fsel || sel.multiple || sel.size > 1) return;
    const btn = document.createElement("span");
    btn.className = "fsel"; btn.tabIndex = 0; btn.setAttribute("role", "combobox");
    btn.setAttribute("aria-label", sel.getAttribute("aria-label") || sel.title || "");
    if ((sel.getAttribute("style") || "").includes("border:0")) btn.classList.add("flat");
    const mw = sel.style.maxWidth || getComputedStyle(sel).maxWidth;
    if (mw && mw !== "none") btn.style.maxWidth = mw;
    sel.parentNode.insertBefore(btn, sel);
    sel.classList.add("fsel-hidden"); sel.tabIndex = -1; sel._fsel = btn;
    btn.addEventListener("mousedown", e => { e.preventDefault(); btn.focus(); open && open.sel === sel ? close() : show(sel, btn); });
    btn.addEventListener("keydown", e => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!open) show(sel, btn); else move(e.key === "ArrowDown" ? 1 : -1);
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (open) { choose(sel, open.idx); close(); } else show(sel, btn);
      } else if (e.key === "Escape" || e.key === "Tab") close();
    });
    btn.addEventListener("blur", () => setTimeout(() => { if (open && open.sel === sel && document.activeElement !== btn) close(); }, 0));
    sel.addEventListener("change", () => sync(sel));
    new MutationObserver(() => sync(sel)).observe(sel, { childList: true, subtree: true, attributes: true, characterData: true });
    sync(sel);
  }

  function scan() { document.querySelectorAll("select").forEach(enhance); }
  // la valeur peut être changée par le code (sel.value = …) sans événement : on remet le texte à jour régulièrement
  setInterval(() => document.querySelectorAll("select").forEach(s => s._fsel && sync(s)), 400);
  // on ne ferme la liste que si c'est ce qui la porte qui défile : avant, le moindre défilement ailleurs (la radio
  // qui descend toute seule à chaque message) la fermait (« le carré des setups disparaît à chaque fois », 23/11)
  addEventListener("scroll", e => {
    if (!open) return;
    const t = e.target;
    if (open.list.contains(t)) return;
    if (t === document || t === document.documentElement || t === document.body || (t.contains && t.contains(open.btn))) close();
  }, true);
  addEventListener("resize", close);
  document.addEventListener("mousedown", e => { if (open && !open.list.contains(e.target) && e.target !== open.btn) close(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan); else scan();
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
})();
