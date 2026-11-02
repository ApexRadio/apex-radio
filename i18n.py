"""
Langue de l'appli (français / anglais).

L("texte français", "English text") renvoie la bonne version selon la langue choisie.
dec("3.6") : virgule décimale en français, point en anglais.
"""

from __future__ import annotations

LANG = "fr"


def set_lang(lang: str) -> None:
    global LANG
    LANG = "en" if str(lang).lower().startswith("en") else "fr"


def en() -> bool:
    return LANG == "en"


def L(fr: str, en_text: str) -> str:
    return en_text if LANG == "en" else fr


def dec(s: str) -> str:
    return s if LANG == "en" else s.replace(".", ",")


def plural(n: float, fr_word: str, en_word: str | None = None) -> str:
    """'1 tour' / '3 tours', '1 lap' / '3 laps'."""
    w = en_word if (LANG == "en" and en_word) else fr_word
    return w + ("s" if abs(n) >= 2 or (LANG == "en" and abs(n) != 1) else "")


def session(code: str) -> str:
    """Nom de session affiché ("course" -> "race"...)."""
    if LANG != "en":
        return code
    return {"course": "race", "qualif": "qualifying", "essais": "practice", "warmup": "warm-up"}.get(code, code)
