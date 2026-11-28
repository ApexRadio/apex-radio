"""
Incidents des autres pilotes : sorties de piste et voitures arrêtées.

- Sortie de piste : la voiture est plus loin du centre que le bord de piste (+1,5 m).
- Voiture arrêtée / très lente en piste (< 10 m/s hors des stands) : tête-à-queue, accident.
On n'annonce que ce qui est DEVANT toi (là où tu vas passer dans le demi-tour qui vient),
avec le numéro du virage, et une seule fois par virage toutes les 25 secondes.
"""

from __future__ import annotations

import time

from i18n import L

AHEAD = 0.25         # on annonce seulement ce qui est juste devant toi (25 % de tour)
GLOBAL_GAP = 20.0    # s : au plus une annonce d'incident toutes les 20 s
ON_TRACK = 9.0       # m : la voiture arrêtée doit être SUR la piste (près de la trajectoire) pour être dangereuse
CONFIRM = 1.0        # s : l'incident doit durer un peu (pas un simple passage sur le vibreur)
OFF_LINE = 14.0      # m : vraiment loin de la trajectoire (les dégagements bitumés ne comptent pas sinon)
COOLDOWN = 25.0      # s : pas deux annonces pour le même virage
SLOW = 10.0          # m/s : voiture quasi arrêtée
YELLOW_AHEAD = 0.22  # tour : un drapeau jaune n'est dit que s'il est à moins de ~1/5 de tour devant toi


class Incidents:
    def __init__(self, behavior) -> None:
        self.beh = behavior          # pour retrouver le numéro du virage
        self.since = {}              # id voiture -> (début, type)
        self.said = {}               # virage -> heure de la dernière annonce
        self.active = []             # pour la carte : [{"x","z","kind"}]
        self.say = None

    def _where(self, f: float) -> str:
        c = self.beh.corner_at(f, ahead=0.015) if self.beh else None
        if c is None and self.beh:
            # hors virage : on donne le virage qui suit
            corners = self.beh.map.corners()
            nxt = min(corners, key=lambda k: (k["start"] - f) % 1, default=None)
            return L(f"avant le virage {nxt['id']}", f"before turn {nxt['id']}") if nxt else L("sur la piste", "on track")
        return L(f"au virage {c}", f"at turn {c}") if c else L("sur la piste", "on track")

    def _sector_start(self, sec: int):
        """Position dans le tour (0..1) où commence le secteur sec (1, 2, 3), d'après la carte apprise."""
        try:
            pts = self.beh.map.points()
            n = len(pts)
            for i in range(n):
                p, q = pts[i - 1], pts[i]
                if p and q and q[2] == sec - 1 and p[2] != sec - 1:
                    return i / n
        except Exception:
            pass
        return None

    def _yellow_dist(self, s, me, sec: int, stopped: list):
        """Distance (en tour) entre toi et le danger. None si on ne sait pas."""
        if not me or "f" not in me:
            return None
        if stopped:
            return min((c["f"] - me["f"]) % 1 for c in stopped)
        if me.get("s") == sec - 1:
            return 0.0                  # tu es déjà dans ce secteur
        st = self._sector_start(sec)
        return None if st is None else (st - me["f"]) % 1

    def yellows(self, s) -> None:
        """Drapeaux jaunes locaux : « Drapeau jaune secteur 2, voiture arrêtée au virage 7 ! »."""
        secs = set(getattr(s, "yellow_sectors", []) or [])
        if not s.on_track or s.yellow or s.in_pits or not self.say:
            self._ysecs = secs
            return
        old = getattr(self, "_ysecs", set())
        now = time.monotonic()
        # Un jaune n'est annoncé que s'il TIENT (2,5 s) : le jeu envoie parfois des jaunes d'une fraction de seconde.
        # Et un secteur qui « clignote » en jaune au même endroit à chaque tour sans voiture arrêtée (remarque d'un
        # joueur au Mans, à Mulsanne) n'est plus annoncé après 2 fois : c'est une fausse info du jeu.
        first = self.__dict__.setdefault("_yfirst", {})
        for x in list(first):
            if x not in secs:
                del first[x]
        for x in secs:
            first.setdefault(x, now)
        done = self.__dict__.setdefault("_ydone", set())      # jaunes déjà traités (annoncés ou écartés) tant qu'ils durent
        done &= secs
        ghost = self.__dict__.setdefault("_yghost", {})      # secteur -> nombre de jaunes sans voiture arrêtée
        # un même secteur n'est pas réannoncé avant 45 s (course hors ligne à Portimão : 40 jaunes en 30 min, 23/11)
        new = [x for x in sorted(secs) if x not in done and now - first[x] >= 2.5 and now - self.said.get(f"y{x}", -99) > 45]
        me = next((c for c in s.cars if c.get("me")), None)
        if me and me.get("spd", 99) < 15:
            # tu es toi-même arrêté ou au ralenti (sortie, tête-à-queue) : ce jaune, c'est sans doute pour toi
            self._ysecs = secs
            return
        import annonces
        if not annonces.get("jaunes"):
            self._ysecs = secs        # le pilote a coupé les annonces de drapeaux jaunes
            return
        ann = self.__dict__.setdefault("_yann", set())   # jaunes vraiment annoncés (pour « levés »)
        mine = me.get("s") if me else None
        for sec in new:
            # seulement les jaunes devant toi (ton secteur ou le suivant) : les autres sont sur la carte,
            # pas besoin de les dire à la radio
            if mine is not None and (sec - 1 - mine) % 3 not in (0, 1):
                done.add(sec)
                continue
            where = ""
            stopped = [c for c in s.cars if not c.get("me") and not c.get("pits") and c.get("s") == sec - 1
                       and (c.get("spd", 99) < SLOW or c.get("off"))]
            # trop loin devant (retours de joueurs, course LGR du 27/11 : « des jaunes qui étaient loin ») :
            # on attend d'être à moins de ~1/5 de tour ; s'il est levé avant, on n'en parle jamais
            d = self._yellow_dist(s, me, sec, stopped)
            if d is not None and d > YELLOW_AHEAD:
                continue
            done.add(sec)
            if not stopped:
                ghost[sec] = ghost.get(sec, 0) + 1
                if ghost[sec] > 2:
                    if ghost[sec] == 3:
                        print(f"  Jaune secteur {sec} : signalé à chaque tour sans voiture arrêtée, je ne l'annonce plus")
                    continue
            ann.add(sec)
            self.said[f"y{sec}"] = now
            if stopped and self.beh:
                if me:
                    stopped.sort(key=lambda c: (c["f"] - me["f"]) % 1)
                w = self._where(stopped[0]["f"])
                self.said[w] = now            # l'annonce « voiture arrêtée » ne se répète pas juste après
                where = L(f", voiture arrêtée {w}", f", car stopped {w}")
            mine = me.get("s") if me else None
            ahead = mine is not None and (sec - 1 - mine) % 3 in (0, 1)
            tail = L(" C'est devant toi, pas de dépassement.", " It's ahead of you, no overtaking.") if ahead else ""
            self.say(None, L(f"Drapeau jaune secteur {sec}{where} !{tail}", f"Yellow flag sector {sec}{where}!{tail}"),
                     urgent=ahead)
        if getattr(self, "_yann", None) and not (secs & self._yann) and now - self.said.get("yclear", -99) > 45:
            # « levés » seulement si on avait annoncé un jaune (sinon « levés » tombait de nulle part)
            self._yann = set()
            self.said["yclear"] = now
            if annonces.get("jaunes_leves"):
                self.say(None, L("Drapeaux jaunes levés, la piste est dégagée.", "Yellows cleared, the track is clear."))
        self._ysecs = secs

    def update(self, s) -> None:
        self.yellows(s)
        if not s.on_track or s.game_phase not in (5, 6) or s.in_pits or s.session == "qualif":
            self.since.clear()
            self.active = []
            return
        now = time.monotonic()
        me = next((c for c in s.cars if c.get("me")), None)
        if me is None or me.get("spd", 99) < 15 or s.game_phase == 6:
            # départ, neutralisation, ou tu es toi-même au ralenti : tout le monde roule doucement
            self.since.clear()
            self.active = []
            return
        active, events = [], []
        for c in s.cars:
            if c.get("me") or c.get("pits") or "off" not in c:
                continue
            off = c["off"]
            if off and self.beh and self.beh.map.saved:
                d = self.beh.map.dist_to_line(c["x"], c["z"], c["f"])
                off = d is not None and d > OFF_LINE
            # seuls les incidents dangereux : voiture arrêtée / très lente SUR la piste
            kind = None
            if c["spd"] < SLOW:
                d = self.beh.map.dist_to_line(c["x"], c["z"], c["f"]) if self.beh and self.beh.map.saved else None
                if d is None or d < ON_TRACK:
                    kind = "arrêt"
            cid = c["id"]
            if kind is None:
                self.since.pop(cid, None)
                continue
            start, k0 = self.since.get(cid, (now, kind))
            if k0 != kind and kind == "arrêt":
                start = now   # une sortie qui se termine à l'arrêt : on repart
            self.since[cid] = (start, kind)
            active.append({"x": c["x"], "z": c["z"], "kind": kind})
            if now - start >= CONFIRM:
                ahead = (c["f"] - me["f"]) % 1
                if ahead < AHEAD:
                    events.append((ahead, kind, c))
        self.active = active
        if not events or not self.say:
            return
        events.sort(key=lambda e: e[0])
        ahead, kind, c = events[0]
        where = self._where(c["f"])
        if now - self.said.get(where, -99) < COOLDOWN or now - self.said.get("*", -99) < GLOBAL_GAP:
            return
        self.said[where] = self.said["*"] = now
        if kind == "arrêt":
            self.say(None, L(f"Attention, voiture arrêtée {where} !", f"Caution, car stopped {where}!"), urgent=True)
        else:
            self.say(None, L(f"Voiture hors piste {where}, attention.", f"Car off {where}, caution."), urgent=True)
