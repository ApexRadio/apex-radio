"""
Côté bureau Windows : fenêtre Apex Radio et icône près de l'horloge.

- Fenêtre : Edge (ou Chrome) en mode application, une vraie fenêtre sans onglets
  ni barre d'adresse, avec l'icône Apex. Sinon, le navigateur par défaut.
- Icône près de l'horloge (pystray) : ouvrir le tableau de bord, radio, silence, quitter.
  Fermer la fenêtre n'arrête pas Apex Radio : la radio continue, on la rouvre par l'icône.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

from i18n import L

HERE = Path(__file__).resolve().parent


def _browser_app() -> str | None:
    """Chemin d'Edge (installé sur tous les Windows 10/11), sinon de Chrome."""
    if sys.platform != "win32":
        return None
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(Path(base) / "Microsoft/Edge/Application/msedge.exe")
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands.append(Path(base) / "Google/Chrome/Application/chrome.exe")
    for c in cands:
        if c.exists():
            return str(c)
    return shutil.which("msedge") or shutil.which("chrome")


def open_window(url: str) -> None:
    """Ouvre le tableau de bord dans sa propre fenêtre."""
    exe = _browser_app()
    if exe:
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1500,920", "--no-first-run",
                              "--no-default-browser-check"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
            return
        except OSError as e:
            print(f"  Fenêtre Apex impossible ({e}), j'ouvre le navigateur.")
    webbrowser.open(url)


def _post(url: str) -> None:
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=b"{}", method="POST"), timeout=3).close()
    except Exception as e:
        print(f"  Action de l'icône impossible ({e.__class__.__name__})")


class Tray:
    """Icône Apex Radio près de l'horloge."""

    def __init__(self, state, base_url: str, phone_url: str, cfg: dict | None = None, save=None) -> None:
        self.state, self.base, self.phone = state, base_url, phone_url
        self.cfg, self.save = cfg, save
        self.icon = None

    def available(self) -> bool:
        try:
            import pystray  # noqa: F401
            from PIL import Image  # noqa: F401
            return True
        except Exception as e:
            print(f"  Icône près de l'horloge indisponible ({e.__class__.__name__}: {e})")
            return False

    def _menu(self):
        import pystray
        v = self.state.voice
        item, sep = pystray.MenuItem, pystray.Menu.SEPARATOR
        return pystray.Menu(
            item(lambda _: L("Ouvrir le tableau de bord", "Open the dashboard"), lambda: open_window(self.base), default=True),
            item(lambda _: L("Vue téléphone : ", "Phone view: ") + self.phone.replace("http://", ""), lambda: open_window(self.phone)),
            sep,
            item(lambda _: "Radio", lambda: _post(self.base + "/api/voice/toggle"), checked=lambda _: bool(v.enabled)),
            item(lambda _: L("Silence (urgent seulement)", "Quiet (urgent only)"), lambda: _post(self.base + "/api/voice/quiet"),
                 checked=lambda _: bool(v.quiet)),
            sep,
            item(lambda _: L("Ouvrir le journal (dépannage)", "Open the log (troubleshooting)"),
                 lambda: os.startfile(HERE / "journal.txt") if hasattr(os, "startfile") else None),
            item(lambda _: L("Quitter Apex Radio", "Quit Apex Radio"), self.quit),
        )

    def quit(self) -> None:
        print("  Arrêt demandé depuis l'icône.")
        try:
            if self.icon:
                self.icon.stop()
        finally:
            threading.Timer(0.3, lambda: os._exit(0)).start()

    def run(self) -> None:
        """Bloque (à appeler sur le fil principal)."""
        import pystray
        from PIL import Image
        img = Image.open(HERE / "apex.ico")
        self.icon = pystray.Icon("ApexRadio", img, "Apex Radio", self._menu())

        def setup(icon) -> None:
            icon.visible = True
            if self.cfg is not None and not self.cfg.get("tray_hint"):
                try:
                    icon.notify(L("Apex Radio tourne ici. Fermer la fenêtre n'arrête pas la radio : "
                                  "clique sur cette icône pour rouvrir le tableau de bord, clic droit pour quitter.",
                                  "Apex Radio runs here. Closing the window keeps the radio on: "
                                  "click this icon to reopen the dashboard, right-click to quit."), "Apex Radio")
                    self.cfg["tray_hint"] = True
                    if self.save:
                        self.save(self.cfg)
                except Exception:
                    pass

        def keep_fresh() -> None:   # coches Radio / Silence et langue à jour, même changées depuis le tableau de bord
            import time
            while True:
                time.sleep(3)
                self.refresh()
        threading.Thread(target=keep_fresh, daemon=True).start()
        self.icon.run(setup=setup)

    def refresh(self) -> None:
        """Après un changement de langue."""
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception:
                pass


def show_existing(base_url: str) -> None:
    """Apex Radio tourne déjà : on rouvre simplement sa fenêtre."""
    open_window(base_url)

