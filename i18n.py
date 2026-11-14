"""
Langue de l'appli.

L("texte français", "English text") renvoie la bonne version selon la langue choisie.
dec("3.6") : virgule décimale en français, point en anglais.

Le français et l'anglais sont écrits dans le code. Les autres langues viennent des fichiers
traductions/<code>.json (créés et mis à jour avec tools/textes.py) : chaque texte français y a
sa traduction, et un texte pas encore traduit retombe sur l'anglais.
Les phrases avec des valeurs (« Freins à {0} degrés ») sont retrouvées même une fois remplies.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

LANG = "fr"
DIR = Path(__file__).resolve().parent / "traductions"

_exact: dict[str, str] = {}                       # texte français -> traduction
_patterns: list[tuple[re.Pattern, str]] = []      # phrases à trous : (motif français, traduction avec {0}, {1}…)
_cache: dict[str, str | None] = {}
_meta: dict = {}


def available() -> dict[str, str]:
    """Langues proposées : {code: nom}. Le français et l'anglais, plus chaque fichier de traductions/."""
    out = {"fr": "Français", "en": "English"}
    try:
        for f in sorted(DIR.glob("*.json")):
            try:
                out[f.stem] = json.loads(f.read_text(encoding="utf-8")).get("_langue", f.stem)
            except (OSError, ValueError):
                pass
    except OSError:
        pass
    return out


def _template_regex(fr: str) -> re.Pattern:
    parts = re.split(r"\{(\d+)\}", fr)
    rx = "".join(re.escape(p) if i % 2 == 0 else f"(?P<v{p}>.*?)" for i, p in enumerate(parts))
    return re.compile("^" + rx + "$", re.S)


def _load(code: str) -> bool:
    global _meta
    try:
        data = json.loads((DIR / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    _exact.clear()
    _patterns.clear()
    _cache.clear()
    _meta = {k: v for k, v in data.items() if k.startswith("_")}
    for e in data.get("textes", []):
        fr, tr = e.get("fr"), (e.get("texte") or "").strip()
        if not fr or not tr:
            continue
        if re.search(r"\{\d+\}", fr):
            fixed = re.sub(r"\{\d+\}", "", fr)
            if sum(c.isalpha() for c in fixed) >= 4:      # « {0} » tout seul attraperait n'importe quoi
                _patterns.append((_template_regex(fr), tr))
        else:
            _exact[fr] = tr
    # les phrases les plus précises d'abord
    _patterns.sort(key=lambda p: -len(re.sub(r"\(\?P<v\d+>\.\*\?\)", "", p[0].pattern)))
    return True


def set_lang(lang: str) -> None:
    global LANG
    code = str(lang or "").lower().split("-")[0].split("_")[0]
    if code in ("fr", "en"):
        LANG = code
    elif code and _load(code):
        LANG = code
    else:
        LANG = "en" if code.startswith("en") else "fr"


def en() -> bool:
    """Vrai pour l'anglais et pour toute langue autre que le français (elles retombent sur l'anglais)."""
    return LANG != "fr"


def _translate(fr: str) -> str | None:
    if fr in _cache:
        return _cache[fr]
    out = _exact.get(fr)
    if out is None:
        for rx, tr in _patterns:
            m = rx.match(fr)
            if m:
                vals = {k[1:]: v for k, v in m.groupdict().items()}
                try:
                    out = re.sub(r"\{(\d+)\}", lambda g: vals.get(g.group(1), g.group(0)), tr)
                except re.error:
                    out = None
                break
    if len(_cache) > 5000:
        _cache.clear()
    _cache[fr] = out
    return out


def L(fr: str, en_text: str) -> str:
    if LANG == "fr":
        return fr
    if LANG == "en":
        return en_text
    return _translate(fr) or en_text


def dec(s: str) -> str:
    comma = LANG == "fr" or (LANG != "en" and _meta.get("_virgule_decimale", False))
    return s.replace(".", ",") if comma else s


def plural(n: float, fr_word: str, en_word: str | None = None) -> str:
    """'1 tour' / '3 tours', '1 lap' / '3 laps'."""
    if LANG == "fr" or not en_word:
        w, english = fr_word, False
    else:
        w, english = (L(fr_word, en_word) if LANG != "en" else en_word), True
        if LANG != "en" and w != en_word:      # mot traduit : la traduction gère elle-même le pluriel
            return w
    return w + ("s" if abs(n) >= 2 or (english and abs(n) != 1) else "")


def session(code: str) -> str:
    """Nom de session affiché ("course" -> "race"...)."""
    if LANG == "fr":
        return code
    return {"course": "race", "qualif": "qualifying", "essais": "practice", "warmup": "warm-up"}.get(code, code)
