// Construit le plugin : regroupe le code dans bin/plugin.js et fabrique les images des touches.
import { build } from "esbuild";
import fs from "node:fs";
import { keyImage } from "./src/images.js";

const P = "com.apexradio.streamdeck.sdPlugin";

await build({
    entryPoints: ["src/plugin.js"],
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node20",
    outfile: `${P}/bin/plugin.js`,
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
});
fs.writeFileSync(`${P}/bin/package.json`, '{ "type": "module" }\n');

// images par défaut des touches (avant qu'Apex réponde), et icônes blanches de la liste des actions
const demo = { lang: "fr", connected: true, on_track: false, radio: "prêt", voice_on: true, quiet: false, spotter: true };
const LIST = {
    radio: "M10 2.5a2.5 2.5 0 0 1 2.5 2.5v4a2.5 2.5 0 0 1-5 0v-4A2.5 2.5 0 0 1 10 2.5zM5.5 9a4.5 4.5 0 0 0 9 0M10 13.5v3M7.5 16.5h5",
    info: "M3 15V9M8 15V5M13 15V11M17 15V3",
    spotter: "M5 10H1.5M3 8l-2 2 2 2M15 10h3.5M17 8l2 2-2 2M10 6a4 4 0 1 1 0 8 4 4 0 0 1 0-8z",
    quiet: "M3 7.5h2.5l3.5-3v11l-3.5-3H3zM12 7.5l5 5M17 7.5l-5 5",
    voice: "M2.5 7.5H5l3.5-3v11l-3.5-3H2.5zM12 7a4 4 0 0 1 0 6M14.5 5a7 7 0 0 1 0 10",
    repeat: "M4 9a6 6 0 0 1 10.5-3.5M15 3v3h-3M16 11a6 6 0 0 1-10.5 3.5M5 17v-3h3",
    ask: "M7.5 7a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M10 14.5v.5",
    launch: "M5 2.5v15M5 3h10l-2.5 3.5L15 10H5",
};
for (const [a, d] of Object.entries(LIST)) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><path d="${d}" fill="none" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    fs.writeFileSync(`${P}/imgs/actions/${a}.svg`, svg);
    fs.writeFileSync(`${P}/imgs/actions/${a}-key.svg`, keyImage(a, demo, { what: "pos" }));
}
fs.writeFileSync(`${P}/imgs/category.svg`,
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 20 20"><path d="${LIST.radio}" fill="none" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`);
console.log("Plugin construit.");
