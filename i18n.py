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
_patterns: list[tuple[re.Pattern, str, str]] = []  # phrases à trous : (motif, traduction avec {0}, {1}…, modèle français)
_cache: dict[str, str | None] = {}
_meta: dict = {}
_intents: list[tuple[str, list[re.Pattern]]] = []   # (question française, tournures de la langue)


_avail: dict[str, str] | None = None


def available() -> dict[str, str]:
    """Langues proposées : {code: nom}. Le français et l'anglais, plus chaque fichier de traductions/."""
    global _avail
    if _avail is not None:
        return _avail
    out = {"fr": "Français", "en": "English"}
    try:
        for f in sorted(p for p in DIR.glob("*.json") if p.name != "intentions.json"):
            try:
                out[f.stem] = json.loads(f.read_text(encoding="utf-8")).get("_langue", f.stem)
            except (OSError, ValueError):
                pass
    except OSError:
        pass
    _avail = out
    return out


def _template_regex(fr: str) -> re.Pattern:
    parts = re.split(r"\{(\d+)\}", fr)
    seen, rx = set(), []
    for i, p in enumerate(parts):
        if i % 2 == 0:
            rx.append(re.escape(p))
        elif p in seen:            # même valeur deux fois : même texte attendu
            rx.append(f"(?P=v{p})")
        else:
            seen.add(p)
            rx.append(f"(?P<v{p}>.*?)")
    return re.compile("^" + "".join(rx) + "$", re.S)


def _plain(text: str) -> str:
    """Minuscules, sans accents ni ponctuation : « Wie viel Sprit ? » -> « wie viel sprit »."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w{}*|]+", " ", t).strip()


def _tournure_regex(t: str) -> list[re.Pattern]:
    """Tournure écrite par le traducteur : des mots (dans l'ordre, d'autres mots peuvent s'intercaler),
    « | » sépare plusieurs façons de dire, « * » = n'importe quel mot, {n} = un nombre (ex. « wo ist p{n} »)."""
    out = []
    for alt in _plain(t).split("|"):
        words = alt.split()
        if not words:
            continue
        parts = [r"(?P<n>\d+)" if w == "{n}" else r"\S+" if w == "*" else
                 re.escape(w).replace(r"\{n\}", r"(?P<n>\d+)") for w in words]
        try:
            out.append(re.compile(r"\b" + r"\s+(?:\S+\s+){0,3}?".join(parts) + r"\b"))
        except re.error:
            pass
    return out


def understand(text: str) -> str:
    """Question dans une autre langue que le français et l'anglais : on reconnaît ses tournures et on la
    transforme en question(s) française(s), qu'Apex sait déjà comprendre. Sans tournure reconnue : texte inchangé."""
    if LANG in ("fr", "en") or not _intents:
        return text
    t = _plain(text)
    out = []
    for fr, rxs in _intents:
        for rx in rxs:
            m = rx.search(t)
            if m:
                n = m.groupdict().get("n")
                q = fr.replace("{n}", n) if n else fr.replace(" {n}", "").replace("{n}", "")
                if q not in out:
                    out.append(q)
                break
    return " et ".join(out) if out else text


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
    _intents.clear()
    for q in data.get("questions", []):
        rx = [r for t in q.get("tournures", []) for r in _tournure_regex(t)]
        if q.get("fr") and rx:
            _intents.append((q["fr"], rx))
    for e in data.get("textes", []):
        fr, tr = e.get("fr"), (e.get("texte") or "").strip()
        if not fr or not tr:
            continue
        if re.search(r"\{\d+\}", fr):
            fixed = re.sub(r"\{\d+\}", "", fr)
            if sum(c.isalpha() for c in fixed) >= 4:      # « {0} » tout seul attraperait n'importe quoi
                _patterns.append((_template_regex(fr), tr, fr))
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


def _value(v: str, depth: int = 0) -> str:
    """Une valeur glissée dans une phrase peut être elle-même un texte français (« survirage », « 1 arrêt ») :
    on la traduit aussi quand on la connaît."""
    if not v or depth > 1 or not any(c.isalpha() for c in v):
        return v
    t = _exact.get(v)
    if t is None and depth == 0:
        t = _translate(v)
    if t is None:
        m = re.match(r"^([\d.,]+ )(.+)$", v)          # « 1 arrêt », « 3 tours »
        if m and m.group(2) in _exact:
            t = m.group(1) + _exact[m.group(2)]
    return t if t is not None else v


def _translate(fr: str) -> str | None:
    if fr in _cache:
        return _cache[fr]
    out = _exact.get(fr)
    if out is None:
        for rx, tr, _fr in _patterns:
            m = rx.match(fr)
            if m:
                vals = {k[1:]: _value(v) for k, v in m.groupdict().items()}
                try:
                    out = re.sub(r"\{(\d+)\}", lambda g: vals.get(g.group(1), g.group(0)), tr)
                except re.error:
                    out = None
                break
    if len(_cache) > 5000:
        _cache.clear()
    _cache[fr] = out
    return out


def catalog() -> dict:
    """Traductions de la langue choisie, pour le tableau de bord (vide en français et en anglais)."""
    if LANG in ("fr", "en"):
        return {"lang": LANG, "exact": {}, "patterns": []}
    return {"lang": LANG, "exact": dict(_exact), "patterns": [[fr, tr] for _rx, tr, fr in _patterns],
            "comma": bool(_meta.get("_virgule_decimale", False))}


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
