"""
Vérification des mises à jour.

Au démarrage (puis toutes les 6 h), on demande à GitHub la dernière version publiée.
Si elle est plus récente que celle installée, le tableau de bord affiche un bandeau
avec un lien vers la page de téléchargement. Rien n'est téléchargé ni installé tout seul.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from pathlib import Path

REPO = "ApexRadio/apex-radio"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
HERE = Path(__file__).resolve().parent


def _num(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def current() -> str:
    try:
        return (HERE / "VERSION").read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


class Updates:
    def __init__(self) -> None:
        self.version = current()
        self.latest: str | None = None
        self.url = PAGE

    def check(self) -> None:
        try:
            req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                                       "User-Agent": "ApexRadio/" + self.version})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.load(r)
            tag = str(d.get("tag_name") or "").lstrip("vV")
            if tag and not d.get("draft") and not d.get("prerelease"):
                self.latest = tag
                self.url = d.get("html_url") or PAGE
                if self.available():
                    print(f"  Mise à jour disponible : {tag} (installée : {self.version})")
        except Exception as e:  # hors ligne, GitHub indisponible… pas grave
            print(f"  Vérification des mises à jour impossible ({e.__class__.__name__})")

    def available(self) -> bool:
        return bool(self.latest) and _num(self.latest) > _num(self.version)

    def start(self) -> None:
        def run() -> None:
            while True:
                self.check()
                time.sleep(6 * 3600)
        threading.Thread(target=run, daemon=True).start()

    def ui(self) -> dict:
        return {"version": self.version, "latest": self.latest if self.available() else None, "url": self.url}
