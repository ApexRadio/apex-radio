"""
Vérification des mises à jour.

Au démarrage (puis toutes les 6 h), on demande à GitHub la dernière version publiée.
Si elle est plus récente que celle installée, l'installateur se télécharge en arrière-plan
(Windows, appli installée), puis le bandeau propose un bouton INSTALLER : rien ne s'installe sans ce clic.
Sinon (ou en cas d'échec), le bandeau garde le lien vers la page de téléchargement.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = "ApexRadio/apex-radio"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
LIST = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
ALL = f"https://github.com/{REPO}/releases"
HERE = Path(__file__).resolve().parent


def _num(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


DISCORD = "https://discord.gg/ZHg4qXd26g"


def test_info() -> dict | None:
    """Version de test (fichier TEST à côté de app.py, seulement dans les zips de test) : nom, numéro, branche."""
    try:
        txt = (HERE / "TEST").read_text(encoding="utf-8")
    except OSError:
        return None
    d = dict(l.split("=", 1) for l in txt.splitlines() if "=" in l)
    d = {k.strip(): v.strip() for k, v in d.items()}
    try:
        d["build"] = int(d.get("build", "0"))
    except ValueError:
        d["build"] = 0
    return d if d.get("branch") else None


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
        self.previous: dict | None = None   # version stable juste avant celle installée (pour revenir en arrière)
        self.asset = None                    # (url, taille, nom) de l'installateur de la dernière version
        self.dl = {"state": None, "pct": 0}  # téléchargement en arrière-plan : None / downloading / ready / error
        self.file: Path | None = None
        self._dl_lock = threading.Lock()
        self.test = test_info()             # version de test (zip donné aux testeurs) ou None
        self.test_new: int | None = None    # numéro de la nouvelle version de test publiée sur GitHub

    def check_test(self) -> None:
        """Version de test : on regarde le fichier TEST de sa branche sur GitHub. Numéro plus grand = nouveau zip."""
        if not self.test:
            return
        url = f"https://raw.githubusercontent.com/{REPO}/{self.test['branch']}/TEST"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ApexRadio/" + self.version})
            with urllib.request.urlopen(req, timeout=8) as r:
                txt = r.read().decode("utf-8", "replace")
            m = re.search(r"build\s*=\s*(\d+)", txt)
            n = int(m.group(1)) if m else 0
            self.test_new = n if n > self.test["build"] else None
            if self.test_new:
                print(f"  Nouvelle version de test {self.test.get('name', '')} : v{n} (installée : v{self.test['build']})")
        except Exception:
            pass

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
                exe = next((a for a in d.get("assets") or [] if str(a.get("name", "")).lower().endswith(".exe")
                            and "setup" in str(a.get("name", "")).lower()), None)
                self.asset = (exe["browser_download_url"], int(exe.get("size") or 0), exe["name"]) if exe else None
                if self.available():
                    print(f"  Mise à jour disponible : {tag} (installée : {self.version})")
                    self.download()
        except Exception as e:  # hors ligne, GitHub indisponible… pas grave
            print(f"  Vérification des mises à jour impossible ({e.__class__.__name__})")

    def check_previous(self) -> None:
        """Cherche la dernière version stable plus ancienne que celle installée (secours si une mise à jour pose problème)."""
        try:
            req = urllib.request.Request(LIST, headers={"Accept": "application/vnd.github+json",
                                                        "User-Agent": "ApexRadio/" + self.version})
            with urllib.request.urlopen(req, timeout=8) as r:
                rels = json.load(r)
            best = None
            for d in rels:
                tag = str(d.get("tag_name") or "").lstrip("vV")
                if not tag or d.get("draft") or d.get("prerelease") or "test" in tag:
                    continue
                if _num(tag) < _num(self.version) and (best is None or _num(tag) > _num(best[0])):
                    best = (tag, d.get("html_url") or ALL)
            self.previous = {"version": best[0], "url": best[1]} if best else None
        except Exception:
            pass

    # ------------------------------------------------------------ téléchargement / installation
    @staticmethod
    def can_install() -> bool:
        """Seulement l'appli installée sous Windows (pas le code source, pas la démo Linux)."""
        return sys.platform == "win32" and (HERE / "unins000.exe").exists()

    def download(self) -> None:
        if self.test or not (self.asset and self.can_install()) or self.dl["state"] in ("downloading", "ready"):
            return
        threading.Thread(target=self._download, daemon=True).start()

    def _download(self) -> None:
        if not self._dl_lock.acquire(blocking=False):
            return
        try:
            from paths import LOCAL
            url, size, name = self.asset
            folder = LOCAL / "maj"
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / name
            if dest.exists() and size and dest.stat().st_size == size:
                self.file, self.dl = dest, {"state": "ready", "pct": 100}
                return
            for old in folder.glob("*.exe"):          # anciens installateurs : on fait le ménage
                try:
                    old.unlink()
                except OSError:
                    pass
            self.dl = {"state": "downloading", "pct": 0}
            print(f"  Mise à jour : téléchargement de {name}…")
            tmp = dest.with_suffix(".part")
            req = urllib.request.Request(url, headers={"User-Agent": "ApexRadio/" + self.version})
            with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
                total = size or int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        self.dl["pct"] = min(99, int(got * 100 / total))
            if total and tmp.stat().st_size != total:
                raise IOError(f"taille {tmp.stat().st_size} au lieu de {total}")
            tmp.replace(dest)
            self.file, self.dl = dest, {"state": "ready", "pct": 100}
            print(f"  Mise à jour : {name} prête à installer.")
        except Exception as e:
            self.dl = {"state": "error", "pct": 0}
            print(f"  Mise à jour : téléchargement impossible ({e!r}), le lien de la page reste disponible.")
        finally:
            self._dl_lock.release()

    def install(self) -> bool:
        """Lance l'installateur (mode silencieux : barre de progression, pas de questions) puis ferme Apex.
        L'installateur relance Apex tout seul à la fin."""
        if not (self.file and self.file.exists() and self.dl["state"] == "ready"):
            return False
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(self.file), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                         close_fds=True, creationflags=flags)
        print(f"  Mise à jour : installation de {self.latest} lancée, Apex se ferme.")
        threading.Timer(1.0, lambda: os._exit(0)).start()
        return True

    def available(self) -> bool:
        return bool(self.latest) and _num(self.latest) > _num(self.version)

    def start(self) -> None:
        def run() -> None:
            while True:
                self.check()
                self.check_previous()
                self.check_test()
                time.sleep(6 * 3600)
        threading.Thread(target=run, daemon=True).start()

    def label(self) -> str:
        if self.test:
            return f"{self.version} · test {self.test.get('name', '')} v{self.test['build']}"
        return self.version

    def ui(self) -> dict:
        out = {"version": self.label(), "latest": self.latest if self.available() else None, "url": self.url,
               "previous": self.previous, "all": ALL, "dl": self.dl if self.available() else None}
        if self.test:
            # version de test : pas de bandeau « télécharge la version officielle » (elle effacerait la version de test)
            out["test"] = {"name": self.test.get("name", ""), "build": self.test["build"], "new": self.test_new,
                           "channel": self.test.get("channel", ""), "official": out["latest"], "discord": DISCORD}
            out["latest"], out["previous"] = None, None
            out["dl"] = None
        return out
