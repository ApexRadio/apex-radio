"""
Piste sèche ou mouillée ? Un tour sous la pluie ne se compare pas à un record fait au sec
(remarque d'un joueur : « elle n'a pas arrêté de dire que j'étais loin de mon meilleur chrono alors que j'étais
sous la pluie »).

Avec une marge (hystérésis) pour ne pas basculer à chaque goutte : on passe « mouillé » à 10 % d'humidité de la
trajectoire, ou s'il pleut franchement, ou en pneus pluie ; on repasse « sec » sous 5 %.
"""

from __future__ import annotations

_WET = False


def wet(s) -> bool:
    global _WET
    w = getattr(s, "wetness", 0.0) or 0.0
    r = getattr(s, "raining", 0.0) or 0.0
    tyres = bool(getattr(s, "wet_tyres", False))
    if _WET:
        _WET = tyres or w >= 0.05 or r >= 0.10
    else:
        _WET = tyres or w >= 0.10 or r >= 0.25
    return _WET


def tag(is_wet: bool) -> str:
    """Suffixe des clés (records, tours de référence) : rien au sec, « pluie » au mouillé."""
    return " | pluie" if is_wet else ""
