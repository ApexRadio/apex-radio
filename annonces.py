"""
Ce que l'ingénieur annonce de lui-même (réglages → Annonces de l'ingé).

Le pilote coche ce qu'il veut entendre, séance par séance. Il peut toujours poser la question :
ces réglages ne coupent que les annonces spontanées, jamais les réponses.
"""

from __future__ import annotations

SESSIONS = ("essais", "qualif", "course")

DEFAULT = {
    # chrono du tour et gain / perte par secteur (record perso, voiture devant)
    "chrono": {"essais": True, "qualif": True, "course": False},
    # écarts avec devant / derrière en course : "chaque" tour, "normal" (de temps en temps), "demande" (jamais tout seul)
    "ecarts": "normal",
    "jaunes": True,          # drapeaux jaunes devant toi
    "jaunes_leves": True,    # « drapeaux jaunes levés »
    "bip": True,             # petit bip quand on appuie sur le bouton radio
}

CFG: dict = {}


def load(saved: dict | None) -> dict:
    """Fusionne le réglage enregistré avec les valeurs par défaut (nouvelles cases = valeur par défaut)."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT.items()}
    for k, v in (saved or {}).items():
        if k not in out:
            continue
        if isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update({s: bool(x) for s, x in v.items() if s in SESSIONS})
        elif k == "ecarts" and v in ("chaque", "normal", "demande"):
            out[k] = v
        elif isinstance(out[k], bool):
            out[k] = bool(v)
    CFG.clear()
    CFG.update(out)
    return out


def _sess(session: str) -> str:
    return session if session in SESSIONS else "essais"     # warm-up et séances inconnues = essais


def chrono(session: str) -> bool:
    return bool((CFG.get("chrono") or DEFAULT["chrono"]).get(_sess(session), True))


def get(key: str):
    return CFG.get(key, DEFAULT.get(key))


load(None)
