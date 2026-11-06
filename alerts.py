"""
Alertes radio supplémentaires :
1. Spotter gauche / droite
2. Trafic multi-catégories (plus rapide qui revient, plus lent à doubler)
3. Tendance des écarts (on revient / on se fait reprendre)
4. Limites de piste
5. Prévisions météo (interface locale de LMU)
8. Dégâts après un contact
"""

from __future__ import annotations

import json
import math
import random
import sys
import threading
import time
import urllib.request

from i18n import L, dec

L_ = L   # dans le trafic, « L » sert aussi à la longueur du circuit


def WHEEL_NAME(i: int) -> str:
    return L("avant gauche|avant droit|arrière gauche|arrière droit", "front left|front right|rear left|rear right").split("|")[i]


def class_name(c: str) -> str:
    u = c.upper()
    for key, name in (("HYPER", "Hypercar"), ("LMH", "Hypercar"), ("LMDH", "Hypercar"), ("GTE", "GTE"), ("GT3", "GT3"),
                      ("LMP2", "LMP2"), ("LMP3", "LMP3")):
        if key in u:
            return name
    return c or L("voiture", "car")


def _dix(x: float) -> str:
    d = round(abs(x) * 10)
    if d >= 10:
        return dec(L(f"{abs(x):.1f} seconde", f"{abs(x):.1f} seconds"))
    return L(f"{max(1, d)} dixième" + ("s" if d > 1 else ""), f"{max(1, d)} tenth" + ("s" if d > 1 else ""))


# ======================================================================= 1. spotter
class Spotter:
    CAR_LEN = 4.8      # m : chevauchement avant/arrière (vraiment côte à côte)
    SIDE_MIN, SIDE_MAX = 0.8, 4.0
    CLEAR_DELAY = 1.0  # s : voie libre depuis 1 s avant de dire « dégagé »
    CONFIRM = 0.35     # s : la voiture doit rester à côté un instant (pas un dépassement éclair)
    SAME_SIDE_GAP = 4.0  # s : on ne répète pas le même côté trop vite

    def __init__(self, voice) -> None:
        self.voice = voice
        self.enabled = True
        self.hist = []          # dernières positions (t, x, z) pour connaître ta direction
        self.state = "clear"
        self.last_seen = {"left": 0.0, "right": 0.0}
        self.left = self.right = False
        self.first_seen = {"left": None, "right": None}
        self.last_said = {}

    def feed(self, m: dict | None) -> None:
        if not m or not self.enabled or getattr(self, "session", "") == "qualif":
            return   # en qualif tu es seul en piste : pas de spotter
        now = time.monotonic()
        x, z = m["me"]
        self.hist.append((now, x, z))
        self.hist = [h for h in self.hist if now - h[0] < 0.35]
        t0, x0, z0 = self.hist[0]
        dx, dz = x - x0, z - z0
        dist = math.hypot(dx, dz)
        if now - t0 < 0.12 or dist / max(now - t0, 1e-3) < 8:   # à l'arrêt / trop lent : pas de spotter
            self._set(False, False, now, quiet=True)
            return
        fx, fz = dx / dist, dz / dist
        lx, lz = -fz, fx            # gauche (repère LMU : x à gauche, y en haut, z vers l'arrière)
        left = right = False
        for ox, oz in m["others"]:
            ddx, ddz = ox - x, oz - z
            along = ddx * fx + ddz * fz
            side = ddx * lx + ddz * lz
            if abs(along) < self.CAR_LEN and self.SIDE_MIN < abs(side) < self.SIDE_MAX:
                if side > 0:
                    left = True
                else:
                    right = True
        for side, here in (("left", left), ("right", right)):
            if here:
                self.last_seen[side] = now
                if self.first_seen[side] is None:
                    self.first_seen[side] = now
            elif now - self.last_seen[side] >= self.CLEAR_DELAY:
                self.first_seen[side] = None
        # confirmé si présent depuis CONFIRM s ; maintenu tant que pas libre depuis CLEAR_DELAY s
        conf = lambda side: self.first_seen[side] is not None and now - self.first_seen[side] >= self.CONFIRM
        left = conf("left") and (left or now - self.last_seen["left"] < self.CLEAR_DELAY)
        right = conf("right") and (right or now - self.last_seen["right"] < self.CLEAR_DELAY)
        self._set(left, right, now)

    def _set(self, left: bool, right: bool, now: float, quiet: bool = False) -> None:
        state = "both" if left and right else "left" if left else "right" if right else "clear"
        if state != self.state and not quiet:
            msg = {"both": L("Des deux côtés !", "Three wide!"), "left": L("À gauche !", "Car left!"),
                   "right": L("À droite !", "Car right!"), "clear": L("Dégagé.", "Clear.")}[state]
            # pas deux fois la même annonce en quelques secondes ; « dégagé » seulement après une vraie annonce
            if now - self.last_said.get(state, -99) >= self.SAME_SIDE_GAP and (state != "clear" or self.state != "clear"):
                self.last_said[state] = now
                self.voice.say(msg, spot=True)
        self.state, self.left, self.right = state, left, right


# ======================================================================= 2. trafic
class Traffic:
    GLOBAL_GAP = 30.0        # s : pas plus d'une annonce de trafic toutes les 30 s

    CATCH_WINDOW = (8.0, 25.0)  # s : on prévient quand on va rattraper une voiture plus lente dans 8 à 25 s

    def __init__(self, behavior=None) -> None:
        self.beh = behavior
        self.said = {}       # (id, type) -> heure
        self.prev_gap = {}
        self.last = -999.0

    def update(self, s, plan, say) -> None:
        if not s.on_track or s.session != "course" or s.in_pits or not s.track_len:
            return
        me = next((c for c in s.cars if c.get("me")), None)
        if not me:
            return
        my_lap = plan.avg_lap or s.last_lap or s.best_lap
        if not my_lap:
            return
        L = s.track_len
        speed = L / my_lap
        # rythme de chaque catégorie (médiane des meilleurs tours)
        bests = {}
        for c in s.cars:
            if c.get("best"):
                bests.setdefault(c["c"], []).append(c["best"])
        pace = {k: sorted(v)[len(v) // 2] for k, v in bests.items()}
        mine = pace.get(me["c"]) or my_lap
        now = time.monotonic()
        if now - self.last < self.GLOBAL_GAP:
            return
        for c in s.cars:
            if c.get("me") or c.get("pits") or c["c"] == me["c"] or c["c"] not in pace:
                continue
            delta = pace[c["c"]] - mine          # < 0 : catégorie plus rapide
            name = class_name(c["cls"])
            if delta < -0.02 * mine:             # plus rapide : on regarde derrière
                gap = ((me["f"] - c["f"]) % 1) * L / speed
                key = (c["id"], "back")
                prev = self.prev_gap.get(key)
                self.prev_gap[key] = gap
                if 1.0 < gap < 3.0 and prev is not None and prev > gap and now - self.said.get(key, -999) > 90:
                    self.said[key] = self.last = now
                    catch = gap / -delta
                    when = L("elle sera sur toi dans ce tour", "it'll be on you this lap") if catch < 1 else \
                        L(f"elle sera sur toi dans {math.ceil(catch)} tours", f"it'll be on you in {math.ceil(catch)} laps")
                    say(None, L(f"{name} qui arrive derrière, {gap:.0f} seconde{'s' if round(gap) > 1 else ''}, {when}.",
                                f"{name} coming up behind, {gap:.0f} second{'s' if round(gap) != 1 else ''}, {when}."))
        self._slower_ahead(s, me, pace, mine, speed, now, say)

    def _slower_ahead(self, s, me, pace, mine, speed, now, say) -> None:
        """Catégorie plus lente devant : on prévient où tu vas la rattraper, pour anticiper le dépassement.
        Une seule annonce à la fois (la plus proche), pas plus d'une fois toutes les 2 minutes par voiture."""
        L = s.track_len
        slow = []
        for c in s.cars:
            if c.get("me") or c.get("pits") or c["c"] == me["c"] or c["c"] not in pace:
                continue
            if pace[c["c"]] - mine <= 0.02 * mine:      # pas nettement plus lente
                continue
            gap = ((c["f"] - me["f"]) % 1) * L / speed  # temps pour arriver là où elle est
            key = (c["id"], "front")
            prev = self.prev_gap.get(key)
            self.prev_gap[key] = gap
            if gap < 8:
                slow.append((gap, prev, c, key))
        slow.sort(key=lambda x: x[0])
        if now - self.last < self.GLOBAL_GAP:
            return
        lo, hi = self.CATCH_WINDOW
        for gap, prev, c, key in slow:
            if prev is None or prev <= gap or now - self.said.get(key, -999) < 120:
                continue
            closing = speed - L / pace[c["c"]]           # m/s gagnés sur elle
            if closing <= 0:
                continue
            t = gap * speed / closing                     # secondes avant de la rattraper
            if not (lo < t < hi):                         # trop tôt (inutile) ou trop tard (déjà dessus)
                continue
            group = [x for x in slow if x[2]["c"] == c["c"] and 0 <= x[0] - gap < 2.0]
            for x in group:
                self.said[x[3]] = now
            self.last = now
            name = class_name(c["cls"])
            corner = self.beh.corner_at((me["f"] + t * speed / L) % 1) if self.beh else None
            where = L_(f", tu la rattrapes au virage {corner}", f", you'll catch it at turn {corner}") if corner else ""
            sec = L_(f"{gap:.0f} seconde{'s' if round(gap) > 1 else ''}", f"{gap:.0f} second{'s' if round(gap) != 1 else ''}")
            if len(group) > 1:
                where = where.replace("la rattrapes", "les rattrapes").replace("catch it", "catch them")
                say(None, L_(f"{len(group)} {name} devant, à {sec}{where}.", f"{len(group)} {name} cars ahead, {sec}{where}."))
            else:
                say(None, L_(f"{name} plus lente devant, à {sec}{where}.", f"Slower {name} ahead, {sec}{where}."))
            return


# ======================================================================= 3. écarts
class GapTrend:
    EVERY = 3

    def __init__(self) -> None:
        self.laps = None
        self.ahead, self.behind = [], []
        self.count = 0

    def update(self, s, say) -> None:
        if not s.on_track or s.session != "course":
            return
        if self.laps is None or s.laps_done < self.laps:
            self.laps = s.laps_done
            self.ahead, self.behind = [], []
            return
        if s.laps_done == self.laps:
            return
        self.laps = s.laps_done
        self.count += 1
        pa = (s.ahead or {}).get("place")
        pb = (s.behind or {}).get("place")
        self.ahead.append((pa, s.gap_class_ahead))
        self.behind.append((pb, s.gap_class_behind))
        self.ahead, self.behind = self.ahead[-4:], self.behind[-4:]
        if self.count % self.EVERY != 1 or s.in_pits:
            return
        msg = self._ahead_msg() or self._behind_msg()
        msg = msg and msg.replace("PNone", L("la voiture", "the car"))
        if msg:
            say(None, msg)

    @staticmethod
    def _rate(series):
        if len(series) < 4 or any(g is None for _, g in series) or len({p for p, _ in series}) != 1:
            return None, None, None   # pas assez de tours, ou ce n'est plus la même voiture
        return (series[-1][1] - series[0][1]) / 3, series[-1][1], series[-1][0]

    # phrases d'ingénieur, tirées au hasard pour ne pas répéter toujours la même chose
    @staticmethod
    def _pep(fr: list[str], en: list[str]) -> str:
        i = random.randrange(len(fr))
        return " " + L(fr[i], en[i])

    def _ahead_msg(self):
        rate, gap, place = self._rate(self.ahead)
        if rate is None or gap > 15:
            return None
        if rate < -0.12:
            if gap < 1.0:
                return L(f"Tu es dans les roues de P{place}, attaque !", f"You're on P{place}'s gearbox, attack!") + self._pep(
                    ["Mets-lui la pression, montre-toi dans ses rétros.", "Il est à portée, cherche l'ouverture au freinage.",
                     "Il commence à craquer, reste collé et attends sa faute."],
                    ["Put him under pressure, show yourself in his mirrors.", "He's in range, look for a gap under braking.",
                     "He's starting to crack, stay close and wait for his mistake."])
            n = math.ceil((gap - 0.8) / -rate)
            return L(f"Tu reprends {_dix(rate)} par tour sur P{place}, dans ses roues dans {n} tour{'s' if n > 1 else ''}.",
                     f"You're gaining {_dix(rate)} a lap on P{place}, on his gearbox in {n} lap{'s' if n > 1 else ''}.") + self._pep(
                    ["Continue comme ça !", "Pousse, il perd du temps !", "Super rythme, va le chercher !",
                     "Il est en difficulté, mets-lui la pression !"],
                    ["Keep it up!", "Push, he's losing time!", "Great pace, go get him!", "He's struggling, put the pressure on!"])
        if rate < -0.05 and gap < 5:
            return L(f"Tu grappilles sur P{place}, petit à petit.", f"You're chipping away at P{place}, bit by bit.") + self._pep(
                ["Continue comme ça.", "Reste régulier, ça va payer."], ["Keep it going.", "Stay consistent, it'll pay off."])
        if rate > 0.15:
            return L(f"P{place} s'échappe de {_dix(rate)} par tour.", f"P{place} is pulling away by {_dix(rate)} a lap.") + self._pep(
                ["Accroche-toi, ne le laisse pas filer.", "Reste concentré, fais ta course.", "Pas de panique, la course est longue."],
                ["Hang on, don't let him go.", "Stay focused, run your own race.", "No panic, it's a long race."])
        return None

    def _behind_msg(self):
        rate, gap, place = self._rate(self.behind)
        if rate is None or gap > 15:
            return None
        if rate < -0.12:
            if gap < 1.0:
                return L(f"P{place} est dans tes roues, défends !", f"P{place} is right behind you, defend!") + self._pep(
                    ["Ferme l'intérieur aux freinages.", "Pas d'erreur, soigne tes sorties de virage.", "Ne lui laisse aucune ouverture."],
                    ["Cover the inside into the braking zones.", "No mistakes, nail your corner exits.", "Don't give him any gap."])
            n = math.ceil((gap - 0.8) / -rate)
            return L(f"P{place} revient de {_dix(rate)} par tour, il sera sur toi dans {n} tour{'s' if n > 1 else ''}.",
                     f"P{place} is closing by {_dix(rate)} a lap, he'll be on you in {n} lap{'s' if n > 1 else ''}.") + self._pep(
                    ["Il est plus rapide, pousse un peu plus.", "Ne lâche rien, garde ton rythme.",
                     "Reste propre, fais tes trajectoires et il ne passera pas."],
                    ["He's quicker, push a bit harder.", "Don't give up, keep your pace.",
                     "Stay clean, hit your lines and he won't get by."])
        if rate > 0.15:
            return L(f"Tu creuses l'écart sur P{place}, {_dix(rate)} par tour.", f"You're pulling away from P{place}, {_dix(rate)} a lap.") + self._pep(
                ["Super boulot, continue comme ça !", "Tu le décroches, garde ce rythme.", "Parfait, il ne peut pas suivre."],
                ["Great job, keep it up!", "You're dropping him, keep this pace.", "Perfect, he can't keep up."])
        return None


# ======================================================================= 4. limites de piste
class TrackLimits:
    def __init__(self, behavior) -> None:
        self.beh = behavior
        self.steps = None

    def update(self, s, say) -> None:
        if not s.on_track:
            return
        if self.steps is None or s.tl_steps < self.steps:
            self.steps = s.tl_steps
            return
        if s.tl_steps > self.steps:
            self.steps = s.tl_steps
            me = next((c for c in s.cars if c.get("me")), None)
            c = self.beh.corner_at(me["f"], ahead=0.01) if me and self.beh else None
            where = L(f" au virage {c}", f" at turn {c}") if c else ""
            if s.tl_per_penalty:
                left = s.tl_per_penalty - s.tl_steps
                if left > 3:
                    say(None, L(f"Limites de piste{where}, avertissement {s.tl_steps} sur {s.tl_per_penalty}.",
                                f"Track limits{where}, warning {s.tl_steps} of {s.tl_per_penalty}."))
                    return
                tail = L("la prochaine, c'est la pénalité !", "next one is a penalty!") if left <= 1 else \
                    L(f"encore {left} avant la pénalité.", f"{left} more before a penalty.")
                say(None, L(f"Limites de piste{where}, avertissement {s.tl_steps} sur {s.tl_per_penalty}, {tail}",
                            f"Track limits{where}, warning {s.tl_steps} of {s.tl_per_penalty}, {tail}"), urgent=left <= 1)
            else:
                say(None, L(f"Limites de piste{where}, avertissement numéro {s.tl_steps}.", f"Track limits{where}, warning number {s.tl_steps}."))


# ======================================================================= 8. dégâts
class Damage:
    def __init__(self) -> None:
        self.dents = None
        self.flat = [False] * 4
        self.wheel_off = [False] * 4
        self.part_off = False
        self.wear = None           # dégâts lus dans l'interface de LMU (aéro, suspensions)
        self.repair = False
        self.choice = None         # choix du pilote à la radio : True / False / None (= Apex décide)
        self._fetching = False
        self._last_fetch = 0.0
        self._session = None

    def update(self, s, say) -> None:
        if not s.on_track:
            return
        key = (s.track, s.session_code)
        if key != self._session:          # nouvelle session : on repart d'une voiture neuve
            self._session = key
            self.repair, self.choice, self.wear, self.dents = False, None, None, None
        me = next((c for c in s.cars if c.get("me")), None)
        moving = me is not None and me.get("spd", 0) > 5 and not s.in_pits
        if self.dents is None or not moving:
            # au garage / au stand / voiture remise en piste : on prend les valeurs sans rien annoncer
            self.dents, self.flat, self.wheel_off, self.part_off = list(s.dents), list(s.flat), list(s.wheel_off), s.part_off
            if s.in_pits and s.pit_state == 3:
                self.repair, self.choice = False, None
            self._apply(s)
            return
        # carrosserie
        if sum(s.dents) > sum(self.dents):
            worst = max(s.dents)
            say(None, L("Contact ! ", "Contact! ")
                + (L("Gros dégâts à la carrosserie.", "Heavy body damage.") if worst >= 2 else L("Dégâts légers à la carrosserie.", "Light body damage."))
                + L(" Je regarde l'aéro et les suspensions.", " Checking aero and suspension."), urgent=True)
            if worst >= 2:
                self.repair = True
            self._last_fetch = 0   # on relit l'interface de LMU tout de suite
        self.dents = list(s.dents)
        # crevaisons, roues
        for i in range(4):
            if s.flat[i] and not self.flat[i]:
                say(None, L(f"Crevaison {WHEEL_NAME(i)} ! Rentre au stand, doucement.", f"Puncture {WHEEL_NAME(i)}! Box, take it easy."), urgent=True)
                self.repair = True
            if s.wheel_off[i] and not self.wheel_off[i]:
                say(None, L(f"Roue {WHEEL_NAME(i)} perdue ! Rentre au stand.", f"Lost the {WHEEL_NAME(i)} wheel! Box now."), urgent=True)
                self.repair = True
        self.flat, self.wheel_off = list(s.flat), list(s.wheel_off)
        if s.part_off and not self.part_off:
            say(None, L("Une pièce s'est détachée de la voiture.", "A part has come off the car."), urgent=True)
        self.part_off = s.part_off
        if s.in_pits and s.pit_state == 3:
            self.repair, self.choice = False, None   # arrêté au stand : on considère que c'est réglé
        self._poll_api(say)
        self._apply(s)

    def _apply(self, s) -> None:
        # plus aucun dégât lisible (voiture réparée ou remise à neuf) : plus rien à réparer
        if self.repair and self.wear is not None and not any(s.flat) and not any(s.wheel_off) and max(s.dents or [0]) == 0:
            aero = self.wear.get("aero") or 0
            susp = [v for v in (self.wear.get("susp") or []) if isinstance(v, (int, float))]
            if aero < 0.05 and all(v < 0.05 for v in susp):
                self.repair = False
        s.repair = self.repair if self.choice is None else self.choice
        s.no_repair = self.choice is False

    def _poll_api(self, say) -> None:
        if sys.platform != "win32" or self._fetching or time.monotonic() - self._last_fetch < 20:
            return
        self._last_fetch = time.monotonic()
        self._fetching = True
        threading.Thread(target=self._fetch, args=(say,), daemon=True).start()

    def _fetch(self, say) -> None:
        try:
            j = lmu_get("/rest/garage/UIScreen/RepairAndRefuel")
            w = (j or {}).get("wearables") or {}
            aero = (w.get("body") or {}).get("aero")
            susp = w.get("suspension") or []
            new = {"aero": aero, "susp": susp[:4]}
            old = self.wear
            self.wear = new
            if old is None:
                return
            if aero is not None and (old.get("aero") or 0) + 0.05 < aero:
                say(None, L(f"Aéro endommagé à {aero * 100:.0f} %.", f"Aero damaged {aero * 100:.0f} %.")
                    + (L(" On répare au prochain arrêt.", " We'll fix it at the next stop.") if aero > 0.15 else ""))
                if aero > 0.15:
                    self.repair = True
            for i, v in enumerate(susp[:4]):
                o = (old.get("susp") or [0, 0, 0, 0])[i] if old.get("susp") else 0
                if isinstance(v, (int, float)) and v > (o or 0) + 0.05:
                    say(None, L(f"Suspension {WHEEL_NAME(i)} touchée à {v * 100:.0f} %. Attention au comportement.",
                                f"{WHEEL_NAME(i).capitalize()} suspension damaged {v * 100:.0f} %. Watch the handling."))
                    if v > 0.15:
                        self.repair = True
        except Exception:
            pass
        finally:
            self._fetching = False


# ======================================================================= 5. météo
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def lmu_get(path: str):
    with _OPENER.open("http://localhost:6397" + path, timeout=2) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


SKY_FR = ["dégagé", "quelques nuages", "nuageux", "couvert", "très couvert", "bruine", "pluie légère",
          "pluie", "forte pluie", "orage", "déluge"]
SKY_EN = ["clear", "few clouds", "cloudy", "overcast", "heavy overcast", "drizzle", "light rain",
          "rain", "heavy rain", "storm", "downpour"]


class Weather:
    NODES = ["START", "NODE_25", "NODE_50", "NODE_75", "FINISH"]

    def __init__(self, demo: bool = False) -> None:
        self.demo = demo
        self.forecast = []          # [{"at": 0..1, "rain": 0..1, "sky": int, "temp": °C}]
        self.said = set()
        self._fetching = False
        self._last = 0.0

    def update(self, s, say) -> None:
        if not s.on_track:
            return
        if self.demo and not self.forecast:
            self.forecast = [{"at": 0.0, "rain": 0.0, "sky": 1, "temp": 21}, {"at": 0.25, "rain": 0.3, "sky": 3, "temp": 20},
                             {"at": 0.5, "rain": 0.8, "sky": 7, "temp": 18}, {"at": 0.75, "rain": 0.4, "sky": 4, "temp": 18},
                             {"at": 1.0, "rain": 0.1, "sky": 2, "temp": 19}]
        elif not self.demo and not self._fetching and time.monotonic() - self._last > 60 and sys.platform == "win32":
            self._last = time.monotonic()
            self._fetching = True
            threading.Thread(target=self._fetch, args=(s.session_code,), daemon=True).start()
        self._announce(s, say)

    def _fetch(self, code: int) -> None:
        try:
            # 1) prévisions de la session en cours (écran Réparation/Ravitaillement de LMU)
            try:
                nodes = ((lmu_get("/rest/garage/UIScreen/RepairAndRefuel") or {}).get("weatherForecast") or {}).get("nodes") or {}
                rain, sky, temp = nodes.get("RainChance") or [], nodes.get("Sky") or [], nodes.get("Temperature") or []
                if rain and sky:
                    n = min(len(rain), len(sky))
                    self.forecast = [{"at": i / max(1, n - 1), "rain": (rain[i] or 0) / 100, "sky": int(sky[i] or 0),
                                      "temp": temp[i] if i < len(temp) else None} for i in range(n)]
                    return
            except Exception:
                pass
            # 2) sinon, prévisions générales par type de session
            key = "PRACTICE" if code <= 4 else "QUALIFY" if code <= 8 else "RACE"
            j = lmu_get("/rest/sessions/weather") or {}
            sess = j.get(key) or {}
            out = []
            for i, name in enumerate(self.NODES):
                n = sess.get(name)
                if not n:
                    continue
                val = lambda k: (n.get(k) or {}).get("currentValue")
                out.append({"at": i / 4, "rain": (val("WNV_RAIN_CHANCE") or 0) / 100, "sky": int(val("WNV_SKY") or 0),
                            "temp": val("WNV_TEMPERATURE")})
            if out:
                self.forecast = out
        except Exception:
            pass
        finally:
            self._fetching = False

    def _announce(self, s, say) -> None:
        if not self.forecast or s.time_left is None:
            return
        total = s.elapsed + s.time_left
        if total <= 0:
            return
        now = s.elapsed / total
        raining = s.raining > 0.1
        for n in self.forecast:
            mins = (n["at"] - now) * total / 60
            if not (2 <= mins <= 20):
                continue
            key = (round(n["at"], 2), "rain" if n["rain"] >= 0.5 else "dry")
            if key in self.said:
                continue
            if not raining and n["rain"] >= 0.5:
                self.said.add(key)
                say(None, L(f"Météo : pluie probable dans environ {mins:.0f} minutes, {n['rain'] * 100:.0f} % de risque.",
                            f"Weather: rain likely in about {mins:.0f} minutes, {n['rain'] * 100:.0f} % chance."))
            elif raining and n["rain"] < 0.2 and n["sky"] <= 3:
                self.said.add(key)
                say(None, L(f"Météo : éclaircie prévue dans environ {mins:.0f} minutes.", f"Weather: drying up in about {mins:.0f} minutes."))

    def ui(self, s) -> list:
        if not self.forecast or s.time_left is None:
            return []
        total = s.elapsed + s.time_left
        out = []
        for n in self.forecast:
            mins = (n["at"] * total - s.elapsed) / 60
            if mins >= -1:
                out.append({"mins": round(mins), "rain": round(n["rain"] * 100), "sky": L("|".join(SKY_FR), "|".join(SKY_EN)).split("|")[max(0, min(10, n["sky"]))]})
        return out[:4]
