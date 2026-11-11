// Images des touches (SVG 144 x 144), style néon d'Apex Radio.
// Pas de filtres SVG (le Stream Deck ne les affiche pas toujours) : la lueur est faite avec des traits superposés.

const CYAN = "#22e3ff";
const RED = "#ff3b5c";
const GREEN = "#2ee59d";
const AMBER = "#ffb02e";
const GREY = "#5b6573";
const FONT = "Arial, Helvetica, sans-serif";

const T = {
    fr: {
        offline: "APEX ?", offline2: "pas lancé", talk: "PARLER", listen: "J'ÉCOUTE", think: "…",
        spotter: "SPOTTER", quiet: "SILENCE", voice: "RADIO", repeat: "RÉPÈTE", launch: "LANCER LMU",
        on: "OUI", off: "NON", ask: "QUESTION", pos: "PLACE", fuel: "ESSENCE", gap_ahead: "DEVANT",
        gap_behind: "DERRIÈRE", box: "BOX", last: "DERNIER", best: "MEILLEUR", laps: "tours", lapsIn: "dans",
        now: "CE TOUR", none: "pas d'arrêt", wait: "en attente",
    },
    en: {
        offline: "APEX ?", offline2: "not running", talk: "TALK", listen: "LISTENING", think: "…",
        spotter: "SPOTTER", quiet: "QUIET", voice: "RADIO", repeat: "REPEAT", launch: "START LMU",
        on: "ON", off: "OFF", ask: "QUESTION", pos: "POSITION", fuel: "FUEL", gap_ahead: "AHEAD",
        gap_behind: "BEHIND", box: "BOX", last: "LAST", best: "BEST", laps: "laps", lapsIn: "in",
        now: "THIS LAP", none: "no stop", wait: "waiting",
    },
};

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function frame(color, inner, dim = false) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144" viewBox="0 0 144 144">
<rect width="144" height="144" fill="#06090f"/>
<rect x="6" y="6" width="132" height="132" rx="18" fill="none" stroke="${color}" stroke-opacity="${dim ? 0.12 : 0.22}" stroke-width="10"/>
<rect x="6" y="6" width="132" height="132" rx="18" fill="#0b111b" stroke="${color}" stroke-opacity="${dim ? 0.45 : 1}" stroke-width="3"/>
${inner}
</svg>`;
}

function text(x, y, s, size, color, weight = "bold", opacity = 1) {
    return `<text x="${x}" y="${y}" font-family="${FONT}" font-size="${size}" font-weight="${weight}" fill="${color}" fill-opacity="${opacity}" text-anchor="middle">${esc(s)}</text>`;
}

// texte qui rétrécit pour tenir dans la touche
function fit(s, max, width = 118) {
    const n = String(s).length || 1;
    return Math.max(12, Math.min(max, Math.floor(width / (n * 0.6))));
}

function glow(path, color, w = 6) {
    return `<g fill="none" stroke-linecap="round" stroke-linejoin="round">
<path d="${path}" stroke="${color}" stroke-opacity="0.25" stroke-width="${w * 2.4}"/>
<path d="${path}" stroke="${color}" stroke-width="${w}"/></g>`;
}

const ICONS = {
    mic: "M72 28 a12 12 0 0 1 12 12 v18 a12 12 0 0 1 -24 0 v-18 a12 12 0 0 1 12 -12 z M48 56 a24 24 0 0 0 48 0 M72 80 v12 M60 92 h24",
    spotter: "M40 58 l-14 0 M34 50 l-8 8 l8 8 M104 58 l14 0 M110 50 l8 8 l-8 8 M72 38 a20 20 0 1 1 -0.1 0 z M72 52 a6 6 0 1 1 -0.1 0 z",
    quiet: "M46 48 h12 l16 -14 v48 l-16 -14 h-12 z M88 46 l20 24 M108 46 l-20 24",
    voice: "M42 48 h12 l16 -14 v48 l-16 -14 h-12 z M84 46 a16 16 0 0 1 0 24 M94 38 a28 28 0 0 1 0 40",
    repeat: "M44 58 a28 28 0 0 1 50 -14 M96 36 v12 h-12 M100 62 a28 28 0 0 1 -50 14 M48 84 v-12 h12",
    launch: "M44 30 v62 M44 32 h46 l-10 14 l10 14 h-46",
    ask: "M58 44 a14 14 0 1 1 20 12 c-5 3 -6 6 -6 12 M72 82 v1",
};

function iconKey(icon, label, color, sub, subColor) {
    return frame(color, `${glow(ICONS[icon], color)}
${text(72, sub ? 112 : 120, label, fit(label, 20), color)}
${sub ? text(72, 131, sub, 13, subColor || color, "bold", 0.85) : ""}`);
}

function fmtGap(g, sign) {
    if (g == null || !isFinite(g)) return "—";
    return (sign > 0 ? "+" : "−") + Math.abs(g).toFixed(1);
}

function fmtLap(t) {
    if (!t || !isFinite(t) || t <= 0) return "—";
    const m = Math.floor(t / 60);
    const s = t - m * 60;
    return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}

function infoKey(what, sd, t) {
    const label = t[what] || t.pos;
    if (!sd) return frame(GREY, `${text(72, 40, label, 16, GREY)}${text(72, 86, t.offline, 26, GREY)}${text(72, 116, t.offline2, 14, GREY)}`, true);
    if (!sd.on_track) return frame(CYAN, `${text(72, 40, label, 16, CYAN, "bold", 0.8)}${text(72, 92, "—", 40, CYAN)}${text(72, 122, t.wait, 13, CYAN, "normal", 0.6)}`, true);
    let big = "—", sub = "", color = CYAN;
    if (what === "pos") {
        big = sd.pos ? `P${sd.pos}` : "—";
        sub = sd.cars ? `/ ${sd.cars}` : "";
    } else if (what === "fuel") {
        big = sd.fuel != null ? `${sd.fuel.toFixed(sd.fuel < 10 ? 1 : 0)} L` : "—";
        if (sd.range_laps == null && sd.energy != null) sub = `⚡ ${Math.round(sd.energy * 100)} %`;
        if (sd.range_laps != null) {
            sub = `≈ ${Math.floor(sd.range_laps)} ${t.laps}`;
            if (sd.range_laps < 2) color = RED;
            else if (sd.range_laps < 4) color = AMBER;
        }
    } else if (what === "gap_ahead") {
        big = fmtGap(sd.gap_ahead, 1);
        if (sd.gap_ahead != null && sd.gap_ahead < 1.0) color = GREEN;   // à portée d'attaque
    } else if (what === "gap_behind") {
        big = fmtGap(sd.gap_behind, -1);
        if (sd.gap_behind != null && sd.gap_behind < 1.0) color = AMBER; // il revient
    } else if (what === "box") {
        if (sd.box_in == null) { big = "—"; sub = t.none; }
        else if (sd.box_in <= 0) { big = t.now; color = RED; }
        else { big = String(sd.box_in); sub = t.laps; color = sd.box_in <= 1 ? AMBER : CYAN; }
    } else if (what === "last" || what === "best") {
        big = fmtLap(what === "last" ? sd.last : sd.best);
    }
    return frame(color, `${text(72, 38, label, 16, color, "bold", 0.85)}
${text(72, 90, big, fit(big, 44, 122), color)}
${sub ? text(72, 122, sub, 15, color, "bold", 0.75) : ""}`);
}

export function keyImage(kind, sd, settings) {
    const t = T[sd && sd.lang === "en" ? "en" : "fr"];
    if (kind === "info") return infoKey(settings.what || "pos", sd, t);
    if (!sd) {
        const icon = { radio: "mic" }[kind] || kind;
        return frame(GREY, `${glow(ICONS[icon] || ICONS.ask, GREY)}${text(72, 112, t.offline, 18, GREY)}${text(72, 131, t.offline2, 12, GREY)}`, true);
    }
    switch (kind) {
        case "radio":
            if (sd.radio === "écoute") return iconKey("mic", t.listen, RED);
            if (sd.radio === "réflexion") return iconKey("mic", t.think, AMBER);
            return iconKey("mic", t.talk, CYAN);
        case "spotter":
            return iconKey("spotter", t.spotter, sd.spotter ? GREEN : GREY, sd.spotter ? t.on : t.off);
        case "quiet":
            return iconKey("quiet", t.quiet, sd.quiet ? AMBER : GREY, sd.quiet ? t.on : t.off);
        case "voice":
            return iconKey("voice", t.voice, sd.voice_on ? GREEN : RED, sd.voice_on ? t.on : t.off);
        case "repeat":
            return iconKey("repeat", t.repeat, CYAN);
        case "launch":
            return iconKey("launch", t.launch, sd.connected ? GREEN : CYAN);
        case "ask": {
            const label = (settings.label || "").trim() || t.ask;
            return iconKey("ask", label.toUpperCase(), CYAN);
        }
    }
    return frame(CYAN, "");
}
