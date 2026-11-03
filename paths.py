"""
Où Apex Radio range ses données.

- DATA  : tes données (records, débriefs, réglages, carburant, cartes, historique des setups)
          -> Documents\\Apex Radio. Faciles à retrouver, à sauvegarder, et partagées par toutes les
          versions installées : une mise à jour ou une réinstallation ne perd rien.
- LOCAL : les gros fichiers techniques (voix, reconnaissance vocale, journal, cache de la fenêtre)
          -> %LOCALAPPDATA%\\Apex Radio.

Mode portable : un fichier « portable.txt » à côté de app.py garde tout dans le dossier de l'appli
(c'est aussi le cas hors Windows). Les variables APEX_DATA / APEX_LOCAL forcent un autre dossier.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent

USER_FILES = ["config.json", "records.json", "fuelbook.json", "setups_history.json"]
USER_DIRS = ["debriefs", "traces", "maps", "setup_backups"]
LOCAL_DIRS = ["models"]


def _documents() -> Path:
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:   # CSIDL_PERSONAL
            return Path(buf.value)
    except Exception:
        pass
    return Path.home() / "Documents"


def _resolve() -> tuple[Path, Path]:
    portable = sys.platform != "win32" or (APP / "portable.txt").exists()
    data = Path(os.environ["APEX_DATA"]) if os.environ.get("APEX_DATA") else (APP if portable else _documents() / "Apex Radio")
    if os.environ.get("APEX_LOCAL"):
        local = Path(os.environ["APEX_LOCAL"])
    elif portable:
        local = APP
    else:
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Apex Radio"
    return data, local


DATA, LOCAL = _resolve()


def migrate() -> list[str]:
    """Reprend les données d'une ancienne version (rangées à côté de app.py), sans jamais écraser."""
    done: list[str] = []
    if DATA == APP and LOCAL == APP:
        return done
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        LOCAL.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"  Dossier de données impossible ({e}) : je reste dans le dossier de l'appli.")
        return done
    for name in USER_FILES:
        src, dst = APP / name, DATA / name
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
            done.append(name)
    for name in USER_DIRS:
        src, dst = APP / name, DATA / name
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst)
            done.append(name + "/")
    for name in LOCAL_DIRS:          # voix et reconnaissance : déplacées (gros fichiers, même disque en général)
        src, dst = APP / name, LOCAL / name
        if src.is_dir() and not dst.exists():
            try:
                shutil.move(str(src), str(dst))
            except OSError:
                shutil.copytree(src, dst, dirs_exist_ok=True)
            done.append(name + "/")
    return done


MIGRATED = migrate()
