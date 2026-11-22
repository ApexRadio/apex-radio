"""
Partage vers Discord.

- Serveur public Apex Radio : on prépare le message (ou le fichier) dans le presse-papiers et on ouvre Discord ;
  le joueur colle (Ctrl+V) avec son propre compte. Pas de lien secret dans l'appli publique.
- Équipe / serveur privé : chaque joueur peut coller dans ⚙️ le webhook de SON salon. Apex y poste alors tout seul
  (message + fichier). Le lien reste sur son PC (config.json), il n'est envoyé nulle part ailleurs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

GUILD = "1566786232422236232"           # serveur Discord Apex Radio
CHANNELS = {                            # salons par jeu (liens donnés par Laurent le 21/11/2026)
    ("lmu", "setups"): "1566787776639406102",
    ("lmu", "chronos"): "1566787790425825310",
    ("acevo", "setups"): "1573709270241902622",
    ("acevo", "chronos"): "1573709338793607311",
}
WEBHOOK_RX = re.compile(r"^https://(?:ptb\.|canary\.)?(?:discord|discordapp)\.com/api/webhooks/\d+/[\w-]+$")

CFG: dict = {}                          # config de l'appli (radio.cfg), branchée par app.py


def webhook() -> str:
    url = str(CFG.get("webhook") or "").strip()
    return url if WEBHOOK_RX.match(url) else ""


def set_webhook(url: str) -> bool:
    from radio import save_config
    url = (url or "").strip()
    if url and not WEBHOOK_RX.match(url):
        return False
    CFG["webhook"] = url
    save_config(CFG)
    return True


def post(content: str, path: Path | None = None) -> tuple[bool, str]:
    """Envoie un message (et un fichier) au webhook de l'équipe."""
    url = webhook()
    if not url:
        return False, "no-webhook"
    payload = json.dumps({"content": content[:1990], "username": "Apex Radio",
                          "allowed_mentions": {"parse": []}}).encode("utf-8")
    try:
        if path and Path(path).exists():
            b = uuid.uuid4().hex
            data = bytearray()
            data += f"--{b}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\nContent-Type: application/json\r\n\r\n".encode()
            data += payload + b"\r\n"
            name = Path(path).name.replace('"', "")
            data += f"--{b}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode("utf-8")
            data += Path(path).read_bytes() + f"\r\n--{b}--\r\n".encode()
            req = urllib.request.Request(url, data=bytes(data), method="POST",
                                         headers={"Content-Type": f"multipart/form-data; boundary={b}", "User-Agent": "ApexRadio"})
        else:
            req = urllib.request.Request(url, data=payload, method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": "ApexRadio"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300, str(r.status)
    except Exception as e:
        return False, e.__class__.__name__


def copy_file(path: Path) -> bool:
    """Met un fichier dans le presse-papiers : Ctrl+V dans Discord le colle comme pièce jointe."""
    if sys.platform != "win32":
        return False
    try:
        p = str(path).replace("'", "''")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -LiteralPath '{p}'"],
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def open_discord(kind: str = "", game: str = "lmu") -> bool:
    """Ouvre le bon salon du serveur Apex Radio (chronos / setups du jeu) dans l'appli Discord, sinon dans le navigateur."""
    ch = CHANNELS.get((game if game in ("lmu", "acevo") else "lmu", kind))
    path = f"{GUILD}/{ch}" if ch else GUILD
    try:
        if sys.platform == "win32":
            os.startfile(f"discord://-/channels/{path}")      # noqa: S606 (protocole de l'appli Discord)
        else:
            import webbrowser
            webbrowser.open(f"https://discord.com/channels/{path}")
        return True
    except Exception:
        try:
            import webbrowser
            webbrowser.open(f"https://discord.com/channels/{path}")
            return True
        except Exception:
            return False


def setup_file(ws, track: str) -> tuple[Path | None, str]:
    """Le fichier setup à partager (le fichier APEX de ce circuit, sinon le setup choisi) et le message qui va avec."""
    from i18n import L
    st = ws.state(track) if ws and track else {}
    folder = st.get("folder")
    name = st.get("apex_file") or st.get("current")
    if not (folder and name):
        return None, ""
    f = Path(st["dir"]) / folder / name
    if not f.exists():
        return None, ""
    car = getattr(ws, "car", "") or ""
    text = (f"🔧 {L('Setup', 'Setup')} · {track}" + (f" · {car}" if car else "") + f"\n📄 {name}"
            + (f"\n🏷️ {st['apex_label']}" if st.get("apex_label") else "") + "\n· Apex Radio")
    return f, text
