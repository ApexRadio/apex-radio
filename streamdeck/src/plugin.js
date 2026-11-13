// Plugin Stream Deck pour Apex Radio.
// Il parle à l'appli Apex Radio sur le même PC (http://127.0.0.1:8765) : rien ne passe par Internet.
import streamDeck, { SingletonAction } from "@elgato/streamdeck";
import { keyImage } from "./images.js";

const APEX = "http://127.0.0.1:8765";
const ID = "com.apexradio.streamdeck";

let sd = null;            // dernier état reçu d'Apex (null = Apex fermé)
const shown = new Map();  // contexte de touche -> dernière image envoyée (on n'envoie que les changements)
const settingsOf = new Map();

async function get(path) {
    try {
        const r = await fetch(APEX + path, { signal: AbortSignal.timeout(900) });
        return r.ok ? await r.json() : null;
    } catch {
        return null;
    }
}

async function post(path, body) {
    try {
        const r = await fetch(APEX + path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body ?? {}),
            signal: AbortSignal.timeout(2000),
        });
        return r.ok;
    } catch {
        return false;
    }
}

class ApexAction extends SingletonAction {
    constructor(name) {
        super();
        this.manifestId = `${ID}.${name}`;
        this.kind = name;
    }
    render(action) {
        const st = settingsOf.get(action.id) || {};
        const svg = keyImage(this.kind, sd, st);
        if (shown.get(action.id) !== svg) {
            shown.set(action.id, svg);
            action.setImage("data:image/svg+xml;charset=utf8," + encodeURIComponent(svg));
        }
    }
    renderAll() {
        for (const a of this.actions) this.render(a);
    }
    onWillAppear(ev) {
        settingsOf.set(ev.action.id, ev.payload.settings || {});
        shown.delete(ev.action.id);
        this.render(ev.action);
    }
    onWillDisappear(ev) {
        shown.delete(ev.action.id);
    }
    onDidReceiveSettings(ev) {
        settingsOf.set(ev.action.id, ev.payload.settings || {});
        this.render(ev.action);
    }
    async press(ev, path, body) {
        if (!(await post(path, body))) {
            await ev.action.showAlert();   // Apex n'est pas lancé
            return;
        }
        await refresh();
    }
}

// Radio : appuyer = parler (comme le bouton du volant). En mode « appuyer une fois », Apex coupe tout seul.
class Radio extends ApexAction {
    constructor() { super("radio"); }
    async onKeyDown(ev) {
        if (!(await post("/api/ptt/down"))) await ev.action.showAlert();
        else refresh();
    }
    async onKeyUp() {
        await post("/api/ptt/up");
        setTimeout(refresh, 150);
    }
}

class Toggle extends ApexAction {
    constructor(name, path) { super(name); this.path = path; }
    onKeyDown(ev) { return this.press(ev, this.path); }
}

class Repeat extends ApexAction {
    constructor() { super("repeat"); }
    onKeyDown(ev) { return this.press(ev, "/api/voice/repeat"); }
}

class Launch extends ApexAction {
    constructor() { super("launch"); }
    async onKeyDown(ev) {
        if (await post("/api/lmu/launch")) await ev.action.showOk();
        else await ev.action.showAlert();
    }
}

// Touche d'info : place, essence, écarts, box, temps au tour. Appuyer = l'ingénieure le dit à la radio.
const SPOKEN = {
    pos: "quelle est ma position",
    fuel: "combien d'essence",
    gap_ahead: "quel écart avec la voiture devant",
    gap_behind: "quel écart avec la voiture derrière",
    box: "quand est-ce que je rentre au stand",
    last: "mon dernier tour",
    best: "mon meilleur tour",
};
const SPOKEN_EN = {
    pos: "what position am I",
    fuel: "how much fuel",
    gap_ahead: "gap to the car ahead",
    gap_behind: "gap to the car behind",
    box: "when do I pit",
    last: "my last lap",
    best: "my best lap",
};
class Info extends ApexAction {
    constructor() { super("info"); }
    onKeyDown(ev) {
        const what = (settingsOf.get(ev.action.id) || {}).what || "pos";
        const words = sd && sd.lang === "en" ? SPOKEN_EN : SPOKEN;
        return this.press(ev, "/api/ask", { q: words[what] || words.pos });
    }
}

// Question libre : la phrase est écrite dans les réglages de la touche.
class Ask extends ApexAction {
    constructor() { super("ask"); }
    onKeyDown(ev) {
        const q = ((settingsOf.get(ev.action.id) || {}).q || "").trim();
        if (!q) return ev.action.showAlert();
        return this.press(ev, "/api/ask", { q });
    }
}

// Commande de la voiture (phares, contact, TC +…) : Apex appuie sur la touche réglée dans LMU par le joueur.
class Car extends ApexAction {
    constructor() { super("car"); }
    onKeyDown(ev) {
        const cmd = (settingsOf.get(ev.action.id) || {}).cmd || "lights";
        return this.press(ev, "/api/lmu/key", { cmd });
    }
}

// Message rapide dans le tchat de LMU (texte réglable sous la touche).
class Chat extends ApexAction {
    constructor() { super("chat"); }
    async onKeyDown(ev) {
        const text = ((settingsOf.get(ev.action.id) || {}).text || "").trim();
        if (!text) return ev.action.showAlert();
        if (await post("/api/lmu/chat", { text })) await ev.action.showOk();
        else await ev.action.showAlert();
    }
}

const ALL = [
    new Car(),
    new Chat(),
    new Radio(),
    new Toggle("spotter", "/api/spotter/toggle"),
    new Toggle("quiet", "/api/voice/quiet"),
    new Toggle("voice", "/api/voice/toggle"),
    new Repeat(),
    new Launch(),
    new Info(),
    new Ask(),
];
for (const a of ALL) streamDeck.actions.registerAction(a);

let busy = false;
async function refresh() {
    if (busy) return;
    busy = true;
    try {
        sd = await get("/api/sd");
        for (const a of ALL) a.renderAll();
    } finally {
        busy = false;
    }
}

streamDeck.connect();
// 4 fois par seconde en piste (phares, contact… réagissent vite) ou pendant que la radio écoute, sinon 1 fois par seconde
(function loop() {
    refresh().finally(() => setTimeout(loop, sd && (sd.radio === "écoute" || sd.on_track) ? 250 : 1000));
})();
