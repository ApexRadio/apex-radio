// Réglages d'une touche (fenêtre sous la touche dans le logiciel Stream Deck).
let ws = null, ctx = "", settings = {};
const fr = () => (navigator.language || "fr").startsWith("fr") ? true : false;
function tr(el) {
    // textes en français ou en anglais selon la langue du logiciel Stream Deck
    document.querySelectorAll("[data-fr]").forEach((e) => { e.textContent = (window.LANG_FR ? e.dataset.fr : e.dataset.en); });
    document.querySelectorAll("[data-ph-fr]").forEach((e) => { e.placeholder = (window.LANG_FR ? e.dataset.phFr : e.dataset.phEn); });
}
function save() {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ event: "setSettings", context: ctx, payload: settings }));
}
// appelée par le logiciel Stream Deck à l'ouverture des réglages
window.connectElgatoStreamDeckSocket = function (port, uuid, registerEvent, info, actionInfo) {
    ctx = uuid;
    try { window.LANG_FR = (JSON.parse(info).application.language || "fr").startsWith("fr"); } catch { window.LANG_FR = true; }
    try { settings = JSON.parse(actionInfo).payload.settings || {}; } catch { settings = {}; }
    ws = new WebSocket("ws://127.0.0.1:" + port);
    ws.onopen = () => ws.send(JSON.stringify({ event: registerEvent, uuid }));
    tr();
    document.querySelectorAll("[data-key]").forEach((el) => {
        const k = el.dataset.key;
        if (settings[k] != null) el.value = settings[k];
        el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => { settings[k] = el.value; save(); });
    });
};
