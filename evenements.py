"""
Journal des événements de course, pour le montage automatique des meilleurs moments (Studio IA de Laurent,
ou tout autre outil).

Chaque lancement d'Apex Radio écrit un fichier  Documents\\Apex Radio\\evenements\\AAAA-MM-JJ_HHhMMmSS.jsonl
Une ligne = un événement, avec l'heure réelle (horloge du PC) pour le caler sur une vidéo OBS :

  {"t": 1764151338.42, "heure": "2026-11-26 11:22:18.420", "type": "depassement", "pos": 4, "places": 1}
  {"t": 1764151351.10, "heure": "...", "type": "radio", "texte": "À gauche !", "spot": true}

Types écrits :
  radio            chaque phrase dite par l'ingé (au moment où elle est dite)
  depassement      une place gagnée en doublant la voiture devant
  gain_places      places gagnées autrement (plusieurs d'un coup, voiture devant aux stands…)
  perte_places     places perdues
  sortie_piste     TA voiture sort de la piste (moi=true)
  tete_a_queue     TA voiture passe de vitesse de course à presque arrêtée en piste (tête-à-queue, accident)
  contact          nouveaux dégâts sur TA voiture
Rien ici ne doit jamais faire planter l'appli : toute erreur est ignorée en silence.
Les fichiers de plus de 30 jours sont effacés au lancement.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime

try:
    from paths import DATA
except Exception:  # tests hors appli
    from pathlib import Path
    DATA = Path(".")

ACTIF = True
GARDE_JOURS = 30
_verrou = threading.Lock()
_fichier = None


def _chemin():
    global _fichier
    if _fichier is None:
        dossier = DATA / "evenements"
        dossier.mkdir(parents=True, exist_ok=True)
        limite = time.time() - GARDE_JOURS * 86400
        for vieux in dossier.glob("*.jsonl"):
            try:
                if vieux.stat().st_mtime < limite:
                    vieux.unlink()
            except OSError:
                pass
        _fichier = dossier / (datetime.now().strftime("%Y-%m-%d_%Hh%Mm%S") + ".jsonl")
    return _fichier


def noter(type_evenement: str, decalage: float = 0.0, **infos) -> None:
    """Note un événement maintenant (ou il y a `decalage` secondes)."""
    if not ACTIF:
        return
    try:
        t = time.time() - max(0.0, decalage)
        ligne = {
            "t": round(t, 3),
            "heure": datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "type": type_evenement,
        }
        ligne.update({k: v for k, v in infos.items() if v is not None})
        with _verrou:
            with open(_chemin(), "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception:
        pass


class MaVoiture:
    """Surveille TA voiture : sorties de piste, tête-à-queue / accident, nouveaux dégâts."""

    OFF_LINE = 14.0      # m loin de la trajectoire = vraiment dehors (comme pour les autres pilotes, incidents.py)
    VITE = 25.0          # m/s : vitesse de course
    ARRET = 8.0          # m/s : presque arrêtée
    FENETRE = 3.0        # s : de VITE à ARRET en moins de ça = tête-à-queue / accident
    PAUSE = 6.0          # s : pas deux fois le même événement à moins de ça

    def __init__(self, beh=None) -> None:
        self.beh = beh
        self.dehors = False
        self.vite_t = None
        self.dents = None
        self.dernier: dict[str, float] = {}

    def _une_fois(self, quoi: str, now: float) -> bool:
        if now - self.dernier.get(quoi, -99) < self.PAUSE:
            return False
        self.dernier[quoi] = now
        return True

    def update(self, s) -> None:
        try:
            self._update(s)
        except Exception:
            pass

    def _update(self, s) -> None:
        if not getattr(s, "on_track", False) or getattr(s, "in_pits", False) or getattr(s, "game_phase", 5) not in (5, 6):
            self.dehors, self.vite_t, self.dents = False, None, None
            return
        now = time.monotonic()
        me = next((c for c in (s.cars or []) if c.get("me")), None)
        # dégâts : une zone de carrosserie qui s'abîme = contact (ou mur)
        dents = list(getattr(s, "dents", []) or [])
        if self.dents is not None and len(dents) == len(self.dents) and any(a > b for a, b in zip(dents, self.dents)):
            if self._une_fois("contact", now):
                noter("contact", moi=True, pos=getattr(s, "position", None))
        self.dents = dents
        if me is None:
            return
        spd = float(me.get("spd", 0) or 0)
        # sortie de piste : le jeu dit « hors piste » ET loin de la trajectoire apprise (si on la connaît)
        off = bool(me.get("off"))
        mp = getattr(self.beh, "map", None) if self.beh else None
        if off and mp is not None and getattr(mp, "saved", False):
            d = mp.dist_to_line(me["x"], me["z"], me["f"])
            off = d is not None and d > self.OFF_LINE
        if off and not self.dehors and spd > 10 and self._une_fois("sortie_piste", now):
            noter("sortie_piste", moi=True, vitesse=round(spd * 3.6), pos=getattr(s, "position", None))
        self.dehors = off
        # tête-à-queue / accident : vitesse de course puis presque arrêtée en quelques secondes
        if spd >= self.VITE:
            self.vite_t = now
        elif spd <= self.ARRET and self.vite_t is not None and now - self.vite_t < self.FENETRE:
            self.vite_t = None
            if getattr(s, "game_phase", 5) == 5 and self._une_fois("tete_a_queue", now):
                noter("tete_a_queue", moi=True, pos=getattr(s, "position", None))
