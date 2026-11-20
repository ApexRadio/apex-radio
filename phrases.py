"""Variété des phrases et ton de la radio.

- pick(clé, variantes) : choisit une formulation au hasard sans reprendre les dernières utilisées.
- dress(texte, ...)    : habille un message selon le ton choisi dans l'appli
                         (« sobre », « radio » d'équipe ou « detente »).
Les messages urgents et le spotter ne sont jamais habillés : ils doivent rester courts.
"""
from __future__ import annotations

import random
from collections import deque

from i18n import L

TONES = ("sobre", "radio", "detente")
TONE = "radio"


def set_tone(tone: str) -> None:
    global TONE
    TONE = tone if tone in TONES else "radio"


DRIVER = ""            # prénom du pilote (Réglages → Ingénieur) : l'ingénieur l'appelle parfois par son prénom
_name_t = 0.0


def set_driver(name: str) -> None:
    global DRIVER
    DRIVER = (name or "").strip()[:24]


def with_name(text: str, answer: bool = False) -> str:
    """« Laurent, 2 places de plus… » : de temps en temps, pas plus d'une fois par minute et demie."""
    global _name_t
    import time as _t
    if not DRIVER or not text or TONE == "sobre":
        return text
    now = _t.monotonic()
    if now - _name_t < 90 or random.random() > (0.35 if answer else 0.2):
        return text
    _name_t = now
    t = text.strip()
    first = t.split(" ", 1)[0]
    keep = len(first) > 1 and (first[1].isupper() or first[1].isdigit() or first[0].isdigit())   # « P3 », « GT3 », « 2 places »
    return f"{DRIVER}, {t if keep else t[:1].lower() + t[1:]}"


# ------------------------------------------------------------------ variantes
_HIST: dict[str, deque] = {}


def pick(key: str, opts: list[tuple[str, str]]) -> str:
    """opts = [(fr, en), ...]. Évite de redire la ou les 2 dernières formulations de cette clé."""
    if not opts:
        return ""
    hist = _HIST.setdefault(key, deque(maxlen=max(1, min(2, len(opts) // 2))))
    free = [i for i in range(len(opts)) if i not in hist] or list(range(len(opts)))
    i = random.choice(free)
    if len(opts) > 1:
        hist.append(i)
    fr, en = opts[i]
    return L(fr, en)


# ------------------------------------------------------------------ habillage
# Toujours terminés par un point : la phrase qui suit garde sa majuscule.
_OPEN = {
    "radio": {
        "info": [("Info radio.", "Radio check."), ("Écoute bien.", "Listen up."), ("OK, info.", "OK, info."),
                 ("Du stand.", "From the pit wall."), ("Petite info.", "Quick one."), ("Pour info.", "Heads up.")],
        "answer": [("Reçu.", "Copy."), ("Bien reçu.", "Copy that."), ("OK, je regarde.", "OK, checking."),
                   ("Copie.", "Copied."), ("Je vérifie.", "Stand by."), ("Reçu, cinq sur cinq.", "Loud and clear.")],
    },
    "detente": {
        "info": [("Alors.", "Right then."), ("Hé, petite info.", "Hey, quick one."), ("Dis donc.", "Hey."),
                 ("Bon.", "So."), ("Tiens, au fait.", "Oh, by the way.")],
        "answer": [("Alors, voyons.", "Let's see."), ("Ah, bonne question.", "Good question."), ("OK.", "OK."),
                   ("Attends, je regarde.", "Hang on, checking."), ("Pas de souci.", "No worries.")],
    },
}
_CLOSE = {
    "radio": [("À toi.", "Over."), ("On reste concentrés.", "Stay focused."), ("Bien reçu ?", "Copy?"),
              ("On continue comme ça.", "Keep it going."), ("Je surveille.", "I'm watching it.")],
    "detente": [("Tranquille.", "Easy."), ("On gère.", "We've got this."), ("Pas de stress.", "No stress."),
                ("Tu assures.", "You're doing great.")],
}
# chances d'ajouter une ouverture / une fin, selon le ton
_RATE = {"radio": (0.35, 0.2), "detente": (0.4, 0.25)}

# réponses qui accusent déjà réception : on n'en rajoute pas
_ALREADY = ("c'est noté", "ok", "reçu", "bien reçu", "compris", "je n'ai", "je t'entends", "radio", "mode silence",
            "spotter", "box", "noted", "copy", "got it", "understood", "i didn't", "i hear")


def dress(text: str, answer: bool = False, urgent: bool = False) -> str:
    """Ajoute parfois une ouverture (« Reçu. », « Info radio. ») et une fin (« À toi. ») selon le ton."""
    if TONE == "sobre" or urgent or not text:
        return text
    named = with_name(text, answer)
    if named != text:
        return named
    low = text.strip().lower()
    if len(low.split()) < 4 or low.startswith(_ALREADY) or "!" in text:
        return text
    p_open, p_close = _RATE[TONE]
    if answer:
        p_open, p_close = p_open + 0.15, p_close * 0.5
    out = text.strip()
    if random.random() < p_open:
        out = pick(f"open:{TONE}:{'answer' if answer else 'info'}", _OPEN[TONE]["answer" if answer else "info"]) + " " + out
    if random.random() < p_close and out.endswith(".") and not any(w in low for w in ("concentr", "continu", "surveill", "à toi")):
        out = out + " " + pick(f"close:{TONE}", _CLOSE[TONE])
    return out
