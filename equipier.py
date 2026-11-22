"""
Mode équipier : quand c'est un coéquipier qui roule (endurance), Apex suit votre voiture d'équipe
dans le classement et annonce l'essentiel : changements de place, passage aux stands.
Le jeu ne donne ni l'essence ni les pneus de la voiture quand ce n'est pas toi qui pilotes.
"""

from __future__ import annotations

import time

from i18n import L


class TeamWatch:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.driver = None
        self.cpos = None
        self.pits = None
        self.stops = None
        self._place_t = 0.0

    def update(self, s, say) -> None:
        tm = getattr(s, "team", None)
        if s.on_track or not tm:
            if s.on_track:
                self.reset()
            return
        from alerts import _driver
        who = _driver(tm.get("driver")) or L("ton équipier", "your teammate")
        if tm.get("driver") != self.driver:
            first = self.driver is None
            self.driver, self.cpos, self.pits, self.stops = tm.get("driver"), tm.get("cpos"), tm.get("pits"), tm.get("stops")
            say(None, L(f"Mode équipier : c'est {who} qui roule, P{tm['cpos']} dans sa catégorie. Je te tiens au courant." if first else
                        f"Changement de pilote : c'est {who} qui roule maintenant, P{tm['cpos']}.",
                        f"Teammate mode: I'm following {who}, P{tm['cpos']} in class." if first else
                        f"Driver change: {who} is driving now, P{tm['cpos']}."))
            return
        if tm.get("pits") and not self.pits:
            say(None, L(f"{who} rentre aux stands.", f"{who} is coming into the pits."))
        elif self.pits and not tm.get("pits") and (tm.get("stops") or 0) > (self.stops or 0):
            say(None, L(f"{who} repart des stands, P{tm['cpos']}.", f"{who} is back out, P{tm['cpos']}."))
        self.pits, self.stops = tm.get("pits"), tm.get("stops")
        c = tm.get("cpos")
        if c and self.cpos and c != self.cpos and not tm.get("pits") and time.monotonic() - self._place_t > 45:
            self._place_t = time.monotonic()
            say(None, L(f"{who} {'gagne' if c < self.cpos else 'perd'} une place, P{c}." if abs(c - self.cpos) == 1 else
                        f"{who} est maintenant P{c}.",
                        f"{who} {'gains' if c < self.cpos else 'loses'} a place, P{c}." if abs(c - self.cpos) == 1 else
                        f"{who} is now P{c}."))
            self.cpos = c
        elif c and not self.cpos:
            self.cpos = c
