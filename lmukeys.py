"""Commandes de la voiture et tchat, envoyés à Le Mans Ultimate comme si on appuyait sur le clavier.

Apex lit les touches que CHAQUE joueur a réglées dans LMU (fichiers de UserData\\Controller ou
UserData\\player), puis appuie dessus avec SendInput en « code de touche physique » (scancode) :
ça marche quelle que soit la disposition du clavier (AZERTY, QWERTY…).
Utilisé par le Stream Deck (touches Voiture, Aides et Tchat).
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path

# commande Apex -> mots qui la reconnaissent dans le nom de la commande LMU (en minuscules)
COMMANDS = {
    "ignition": [r"ignition"],
    "starter": [r"starter"],
    "limiter": [r"limiter"],
    "lights": [r"headlight"],
    "flash": [r"flash|pass(ing)? light"],
    "wipers": [r"wiper"],
    "neutral": [r"neutral"],
    "pit_request": [r"request pit|pit request"],
    # réglages + / - : (sujet, sens, mots à exclure), dans n'importe quel ordre dans le nom
    "tc_up": (r"traction|\btc\b", "up", r"slip|cut|power"),
    "tc_down": (r"traction|\btc\b", "down", r"slip|cut|power"),
    "tccut_up": (r"cut|power", "up", None),
    "tccut_down": (r"cut|power", "down", None),
    "tcslip_up": (r"slip", "up", None),
    "tcslip_down": (r"slip", "down", None),
    "abs_up": (r"\babs\b|anti.?lock", "up", None),
    "abs_down": (r"\babs\b|anti.?lock", "down", None),
    "bias_fwd": (r"bias", "fwd", None),
    "bias_rear": (r"bias", "rear", None),
    "map_up": (r"(engine|motor) ?map|mixture", "up", None),
    "map_down": (r"(engine|motor) ?map|mixture", "down", None),
    "regen_up": (r"regen", "up", None),
    "regen_down": (r"regen", "down", None),
    "chat": [r"\bchat\b|talk"],
}
DIRS = {"up": r"\b(up|incr\w*|plus|next|raise)\b|\+", "down": r"\b(down|decr\w*|minus|prev\w*|lower)\b|(?<![a-z])-(?![a-z])",
        "fwd": r"forw\w*|front|fwd", "rear": r"rear\w*|back\w*|bwd"}
HOLD = {"starter": 1.5}          # secondes : le démarreur doit rester enfoncé
CHAT_DEFAULT = 0x14              # T, la touche de tchat par défaut
ENTER, ESC = 0x1C, 0x01

_map: dict[str, int] = {}        # commande -> code de touche LMU (DirectInput = scancode)
_names: dict[str, str] = {}      # commande -> nom de la commande dans LMU (pour le journal)
_loaded_from = ""
_lock = threading.Lock()


def _candidates(user_data: Path) -> list[Path]:
    out = []
    for d in (user_data / "Controller", user_data / "player"):
        try:
            out += [p for p in d.glob("*.json") if p.is_file()]
        except OSError:
            pass
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def _keyboard_code(v) -> int | None:
    """Les réglages LMU ressemblent à [appareil, code] ; l'appareil 0 = le clavier."""
    if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v):
        dev, code = v
        if dev == 0 and 0 < code < 256:
            return code
    if isinstance(v, dict):
        for k in ("keyboard", "Keyboard", "key", "Key"):
            if isinstance(v.get(k), int) and 0 < v[k] < 256:
                return v[k]
    return None


def _walk(node, found: dict):
    if isinstance(node, dict):
        for k, v in node.items():
            code = _keyboard_code(v)
            if code is not None and isinstance(k, str):
                found.setdefault(k, code)
            else:
                _walk(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk(v, found)


def load(user_data: str | Path | None = None, verbose: bool = True) -> int:
    """Lit les touches de LMU. Renvoie le nombre de commandes Apex trouvées."""
    global _loaded_from
    if user_data is None:
        try:
            import setups
            user_data = Path(setups.find_settings_dir()).parent.parent
        except Exception:
            return 0
    found: dict[str, int] = {}
    src = ""
    for f in _candidates(Path(user_data)):
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        before = len(found)
        _walk(data, found)
        if len(found) > before and not src:
            src = f.name
    with _lock:
        _map.clear()
        _names.clear()
        for cmd, pats in COMMANDS.items():
            for name, code in found.items():
                low = re.sub(r"^control\s*-\s*", "", name.lower().replace("_", " "))
                if isinstance(pats, tuple):
                    subj, d, excl = pats
                    ok = re.search(subj, low) and re.search(DIRS[d], low) and not (excl and re.search(excl, low))
                else:
                    ok = any(re.search(p, low) for p in pats)
                if ok:
                    _map[cmd], _names[cmd] = code, name
                    break
        _loaded_from = src
    if verbose:
        if _map:
            print(f"  Touches LMU ({src}) : " + ", ".join(f"{c}={_names[c]}" for c in _map))
        else:
            print("  Touches LMU : aucune touche clavier trouvée (Stream Deck : commandes voiture indisponibles)")
        if found and len(_map) < 6:   # pour régler la reconnaissance des noms
            print("  Commandes clavier LMU : " + ", ".join(sorted(found)[:60]))
    return len(_map)


def available() -> list[str]:
    return sorted(_map)


# ------------------------------------------------------------------ envoi des touches (Windows)
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _KEYUP, _SCAN, _UNICODE, _EXT = 0x0002, 0x0008, 0x0004, 0x0001
    ULONG_PTR = ctypes.c_size_t

    class _KI(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _MI(ctypes.Structure):   # pour que l'union ait la bonne taille
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _U(ctypes.Union):
        _fields_ = [("ki", _KI), ("mi", _MI)]

    class _IN(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    def _send(scan: int = 0, up: bool = False, char: str | None = None) -> None:
        if char is not None:
            ki = _KI(0, ord(char), _UNICODE | (_KEYUP if up else 0), 0, 0)
        else:
            ki = _KI(0, scan & 0x7F, _SCAN | (_EXT if scan & 0x80 else 0) | (_KEYUP if up else 0), 0, 0)
        inp = _IN(1, _U(ki=ki))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_IN))
else:
    def _send(scan: int = 0, up: bool = False, char: str | None = None) -> None:
        print(f"  (touche simulée hors Windows : {char or hex(scan)} {'relâchée' if up else 'enfoncée'})")


def _tap(code: int, hold: float = 0.06) -> None:
    _send(code)
    time.sleep(hold)
    _send(code, up=True)


def press(cmd: str) -> bool:
    """Appuie sur la touche LMU de cette commande. False si le joueur ne l'a pas réglée au clavier."""
    if not _map:
        load(verbose=False)
    code = _map.get(cmd)
    if code is None:
        return False
    threading.Thread(target=_tap, args=(code, HOLD.get(cmd, 0.06)), daemon=True).start()
    return True


def chat(text: str) -> bool:
    """Ouvre le tchat de LMU, tape le message et l'envoie."""
    text = (text or "").strip()[:120]
    if not text:
        return False
    if not _map:
        load(verbose=False)
    key = _map.get("chat", CHAT_DEFAULT)

    def run():
        _tap(key)
        time.sleep(0.25)
        for ch in text:
            _send(char=ch)
            _send(char=ch, up=True)
            time.sleep(0.008)
        time.sleep(0.05)
        _tap(ENTER)

    threading.Thread(target=run, daemon=True).start()
    return True
