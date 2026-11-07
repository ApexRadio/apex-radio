"""Annonce automatique d'une nouvelle version dans le salon Discord (via un webhook).

Lancé par le workflow « Installateur Windows » après la publication sur `main`.
Le texte vient de installer/release-notes.md (la section « 🆕 <version> »), donc rien à écrire en plus.
Le lien du webhook est un secret GitHub (DISCORD_WEBHOOK) : sans lui, on ne fait rien.
"""
import json
import os
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPO = "https://github.com/ApexRadio/apex-radio"


def notes(version: str) -> tuple[list[str], list[str]]:
    """Lignes françaises et anglaises de la section de cette version."""
    text = (ROOT / "installer" / "release-notes.md").read_text(encoding="utf-8")
    fr, en, inside = [], [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = version in line
            continue
        if inside and line.strip().startswith("-"):
            item = line.strip()[1:].strip()
            if item.startswith("🇫🇷"):
                fr.append("• " + item.replace("🇫🇷", "", 1).strip())
            elif item.startswith("🇬🇧"):
                en.append("• " + item.replace("🇬🇧", "", 1).strip())
    return fr, en


def clip(lines: list[str], limit: int) -> str:
    out = ""
    for l in lines:
        if len(out) + len(l) + 1 > limit:
            return out + "…"
        out += l + "\n"
    return out.strip()


def main() -> int:
    hook = os.environ.get("DISCORD_WEBHOOK", "").strip()
    if not hook:
        print("Pas de webhook Discord configuré (secret DISCORD_WEBHOOK) : pas d'annonce.")
        return 0
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    fr, en = notes(version)
    if not fr and not en:
        print(f"Aucune note trouvée pour {version} dans release-notes.md : pas d'annonce.")
        return 0
    url = f"{REPO}/releases/tag/v{version}"
    embeds = []
    if fr:
        embeds.append({"title": f"🇫🇷 Nouveautés de la {version}", "description": clip(fr, 3900), "color": 0x00E5FF, "url": url})
    if en:
        embeds.append({"title": f"🇬🇧 What's new in {version}", "description": clip(en, 3900), "color": 0x00E5FF, "url": url})
    payload = {
        "username": "Apex Radio",
        "content": (f"🆕 **Apex Radio {version} est sortie ! / Apex Radio {version} is out!**\n"
                    f"👉 {REPO}/releases/latest\n"
                    "Le bandeau de mise à jour te la propose dans l'appli / The update banner offers it in the app. 🏁"),
        "embeds": embeds,
        "allowed_mentions": {"parse": []},
    }
    req = urllib.request.Request(hook, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "ApexRadio-release"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"Annonce Discord envoyée ({r.status}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
