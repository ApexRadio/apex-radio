"""Annonce automatique d'une nouvelle version dans le salon Discord (via un webhook).

Lancé par le workflow « Installateur Windows » :
- après la publication sur `main` → #annonces-news (secret DISCORD_WEBHOOK) ;
- avec `--early`, pour une version de test → #accès-anticipé, réservé aux membres Pit Wall et Écurie
  (secret DISCORD_WEBHOOK_EARLY).
Le texte vient de installer/release-notes.md (la section « 🆕 <version> »), donc rien à écrire en plus.
Les liens des webhooks sont des secrets GitHub : sans eux, on ne fait rien.
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
    early = "--early" in sys.argv
    var = "DISCORD_WEBHOOK_EARLY" if early else "DISCORD_WEBHOOK"
    hook = os.environ.get(var, "").strip()
    if not hook:
        print(f"Pas de webhook Discord configuré (secret {var}) : pas d'annonce.")
        return 0
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    fr, en = notes(version)
    if not fr and not en:
        print(f"Aucune note trouvée pour {version} dans release-notes.md : pas d'annonce.")
        return 0
    url = f"{REPO}/releases/tag/v{version}" + ("-test" if early else "")
    embeds = []
    if fr:
        embeds.append({"title": f"🇫🇷 Nouveautés de la {version}", "description": clip(fr, 3900), "color": 0x00E5FF, "url": url})
    if en:
        embeds.append({"title": f"🇬🇧 What's new in {version}", "description": clip(en, 3900), "color": 0x00E5FF, "url": url})
    if early:
        content = (f"🧪 **Accès anticipé : Apex Radio {version} (version de test) / Early access: Apex Radio {version} (test build)**\n"
                   f"Merci pour ton soutien ! Tu l'as avant tout le monde / Thanks for your support, you get it before everyone else.\n"
                   f"👉 {url}  (ApexRadio-Setup-{version}.exe, en bas de la page / at the bottom of the page)\n"
                   "Un souci ou une idée ? Dis-le ici / Any issue or idea? Tell us here. 🏁")
    else:
        content = (f"🆕 **Apex Radio {version} est sortie ! / Apex Radio {version} is out!**\n"
                   f"👉 {REPO}/releases/latest\n"
                   "Le bandeau de mise à jour te la propose dans l'appli / The update banner offers it in the app. 🏁")
    payload = {
        "username": "Apex Radio",
        "content": content,
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
