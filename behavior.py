"""
Comportement de la voiture : analyse virage par virage + conseils de réglage.

Reçoit ~50 mesures par seconde (lecture rapide) et repère :
- sous-virage / survirage, en entrée (freinage), milieu ou sortie (accélération)
  en comparant le glissement des pneus avant et arrière ;
- blocages de roues au freinage, patinage en sortie ;
- températures des pneus intérieur / milieu / extérieur (carrossage, pression) ;
- fond plat qui touche.
Un problème n'est annoncé que s'il revient sur 2 des 3 derniers tours.
"""

from __future__ import annotations

import threading
import time

from i18n import L, dec
from collections import defaultdict, deque

MIN_SPEED = 15.0       # m/s : en dessous, on ignore (stand, épingles très lentes)
CORNER_LAT = 7.0       # m/s² : on est en virage
UNDER = 0.03           # rad : avant glisse plus que l'arrière -> sous-virage (avant d'avoir une référence)
OVER = -0.025          # rad : arrière glisse plus -> survirage
REL = 0.025            # rad : écart à l'équilibre habituel de LA voiture, virage par virage
GLOBAL_UNDER = 0.04    # équilibre moyen au-delà duquel la voiture est "globalement sous-vireuse"
GLOBAL_OVER = -0.025
SAY_EVERY = 3          # au plus une annonce de comportement tous les 3 tours
LOCK = -0.18           # taux de glissement : roue bloquée
FAST_V = 42.0          # m/s (~150 km/h) : vitesse mini au-delà de laquelle un virage est « rapide » (l'aéro compte plus)
COLD_TYRE = 55.0       # °C : pneus avant froids, un blocage ne veut rien dire
COLD_BRAKE = 180.0     # °C : freins avant froids
LOCK_DRIVING = 2       # blocage dans 1 ou 2 virages seulement : conseil de pilotage, pas de réglage
HOLD_LAPS = 3          # après un changement de réglage, on attend 3 tours avant de juger
SPIN = 0.15            # taux de glissement : patinage
WHEEL = ["avant gauche", "avant droit", "arrière gauche", "arrière droit"]
PHASES = ["entrée", "milieu", "sortie"]

TIPS = {
    ("sous-virage", "entrée"): "recule un peu la répartition de freinage, ou assouplis la barre antiroulis avant",
    ("sous-virage", "milieu"): "assouplis la barre antiroulis avant, ou ajoute un cran d'aileron avant",
    ("sous-virage", "sortie"): "réduis le blocage du différentiel en accélération, ou assouplis l'avant",
    ("survirage", "entrée"): "avance un peu la répartition de freinage, ou réduis le frein moteur",
    ("survirage", "milieu"): "assouplis la barre antiroulis arrière, ou ajoute un cran d'aileron arrière",
    ("survirage", "sortie"): "monte le contrôle de traction d'un cran, ou assouplis la barre antiroulis arrière",
    ("blocage", "avant"): "recule la répartition de freinage d'un demi-point",
    ("blocage", "arrière"): "avance la répartition de freinage d'un demi-point",
    ("patinage", ""): "monte le contrôle de traction d'un cran, ou sois plus progressif à l'accélération",
    ("surbraquage", ""): "tu tournes trop le volant, l'avant décroche et la voiture freine : moins d'angle, l'avant accrochera mieux",
}
OVERDRIVE_ALPHA = 0.13   # rad (~7,5°) : au-delà, les pneus avant ont dépassé leur adhérence maxi
MAX_REPEAT = 2           # un même conseil n'est pas répété plus de 2 fois si on ne le suit pas
# ce qui se règle EN PISTE (dans la voiture) ; le reste se règle au garage
IN_CAR = {("blocage", None), ("sous-virage", "entrée"), ("survirage", "entrée"), ("survirage", "sortie"),
          ("patinage", None), ("surbraquage", None)}
GARAGE_TIPS = {
    ("sous-virage", "milieu"): "barre antiroulis avant plus souple",
    ("sous-virage", "sortie"): "différentiel moins bloqué en accélération, ou barre antiroulis avant plus souple",
    ("sous-virage", "entrée"): "barre antiroulis avant plus souple",
    ("survirage", "milieu"): "barre antiroulis arrière plus souple, ou un cran d'aileron arrière",
    ("survirage", "sortie"): "barre antiroulis arrière plus souple",
    ("survirage", "entrée"): "plus de blocage du différentiel au lever de pied",
    ("blocage", None): "",
    ("patinage", None): "",
    ("surbraquage", None): "",
}


TIPS_EN = {
    ("sous-virage", "entrée"): "move the brake bias back a little, or soften the front anti-roll bar",
    ("sous-virage", "milieu"): "soften the front anti-roll bar, or add a click of front wing",
    ("sous-virage", "sortie"): "reduce the diff power lock, or soften the front",
    ("survirage", "entrée"): "move the brake bias forward a little, or reduce engine braking",
    ("survirage", "milieu"): "soften the rear anti-roll bar, or add a click of rear wing",
    ("survirage", "sortie"): "one more click of traction control, or soften the rear anti-roll bar",
    ("blocage", "avant"): "move the brake bias back half a point",
    ("blocage", "arrière"): "move the brake bias forward half a point",
    ("patinage", ""): "one more click of traction control, or be smoother on the throttle",
    ("surbraquage", ""): "too much steering lock, the front lets go and scrubs speed: less angle and the front will grip better",
}
GARAGE_TIPS_EN = {
    ("sous-virage", "milieu"): "softer front anti-roll bar",
    ("sous-virage", "sortie"): "less diff power lock, or softer front anti-roll bar",
    ("sous-virage", "entrée"): "softer front anti-roll bar",
    ("survirage", "milieu"): "softer rear anti-roll bar, or a click of rear wing",
    ("survirage", "sortie"): "softer rear anti-roll bar",
    ("survirage", "entrée"): "more diff coast lock",
}
KIND_EN = {"sous-virage": "understeer", "survirage": "oversteer", "blocage": "lock-up", "patinage": "wheelspin",
           "surbraquage": "overdriving"}
PHASE_EN = {"entrée": "entry", "milieu": "mid-corner", "sortie": "exit"}
WHEEL_EN = ["front left", "front right", "rear left", "rear right"]


def _wheel_en(w: str) -> str:
    return WHEEL_EN[WHEEL.index(w)] if w in WHEEL else {"avant": "front", "arrière": "rear"}.get(w, w)


def _tip(k: str, w: str) -> str:
    return L(TIPS[(k, w)], TIPS_EN[(k, w)])


def _garage(k: str, w) -> str:
    fr = GARAGE_TIPS.get((k, w)) or GARAGE_TIPS.get((k, None)) or ""
    if not fr:
        return ""
    return L(fr, GARAGE_TIPS_EN.get((k, w)) or fr)


def _in_car(k: str, w: str) -> bool:
    return (k, None) in IN_CAR or (k, w) in IN_CAR
# quels problèmes dépendent de quel réglage de la voiture (pour repartir de zéro quand tu le changes)
LINKED = {"bias": {("blocage", None), ("sous-virage", "entrée"), ("survirage", "entrée")},
          "tc": {("patinage", None), ("survirage", "sortie")},
          "farb": {("sous-virage", "milieu"), ("sous-virage", "sortie"), ("sous-virage", "entrée")},
          "rarb": {("survirage", "milieu"), ("survirage", "sortie")}}
CTRL_NAME = {"bias": "Répartition de freinage", "tc": "Contrôle de traction", "abs": "ABS",
             "farb": "Barre antiroulis avant", "rarb": "Barre antiroulis arrière"}
CTRL_NAME_EN = {"bias": "Brake bias", "tc": "Traction control", "abs": "ABS",
                "farb": "Front anti-roll bar", "rarb": "Rear anti-roll bar"}


class Behavior:
    def __init__(self, trackmap) -> None:
        self.map = trackmap
        self.lock = threading.Lock()
        self._lap = None
        self._new_lap()
        self.history: deque = deque(maxlen=3)   # problèmes des 3 derniers tours
        self.announced: dict = {}               # problème -> numéro de tour annoncé
        self.issues: list = []                  # problèmes confirmés (pour l'UI / les questions)
        self.tyre_tips: list = []
        self.tyre_findings: list = []
        self.say = None
        self.laps_seen = 0
        self.base = None                        # équilibre habituel de la voiture (médiane)
        self.base_hist: deque = deque(maxlen=3)
        self.last_say = -99
        self.group_said: dict = {}              # (type, phase) -> (virages, tour)
        self.tyre_said = (None, -99)
        self.ctrl = {}                          # réglages lus en direct dans la voiture
        self.ctrl_pending = {}                  # changement en cours (on attend qu'il soit stable)
        self.ctrl_track = None                  # circuit sur lequel ces réglages ont été lus
        self.repeats = defaultdict(int)         # nombre de fois qu'un conseil a été donné
        self.bias_front = None
        self.garage_notes = {}                  # problème -> conseil garage (pour la fin de course)
        self.garage_said = -9999.0              # dernière annonce « ça se corrige au garage »
        self.bias_start = None                  # répartition au début du relais (on ne la fait pas dériver sans fin)
        self.bias_done = False                  # répartition déjà changée sur ce circuit : on n'y retouche plus
        self.hold_until = 0                     # pas d'annonce avant ce tour (on laisse le temps de juger un changement)
        self.corner_v = {}                      # virage -> vitesse mini habituelle (m/s), pour virages lents / rapides
        self.brake_peaks = None                 # [avant, arrière] : pic de température des freins par tour (médiane)
        self.brake_hist: deque = deque(maxlen=3)
        self.sgn = {1: 0, -1: 0}                # sens habituel volant / virage (pour repérer le contre-braquage)
        self.driver_issue = None                # ce que le pilote a signalé lui-même (« l'arrière glisse »)

    def live_controls(self, track: str) -> dict:
        """Réglages de la voiture lus en piste (pour les reporter dans le fichier de setup)."""
        if not self.ctrl or self.ctrl_track != track:
            return {}
        out = {}
        if self.ctrl.get("bias"):
            out["bias_front"] = round((1 - self.ctrl["bias"]) * 100, 1)
        for k in ("tc", "abs"):
            if self.ctrl.get(k):
                out[k] = int(round(self.ctrl[k]))
        return out

    def reset_analysis(self) -> None:
        """Nouveau setup chargé : on repart de zéro pour juger ce setup-là."""
        with self.lock:
            self.history.clear()
            self.announced.clear()
            self.issues = []
            self.tyre_tips = []
            self.tyre_findings = []
            self.laps_seen = 0
            self.driver_issue = None
            self.base = None
            self.base_hist.clear()
            self.group_said.clear()
            self.tyre_said = (None, -99)
            self.dirty = True   # le tour en cours ne compte pas
            self.bias_start = None

    def _new_lap(self) -> None:
        self.cur = defaultdict(lambda: [0, 0, 0])        # (virage, phase) -> [n, sous, sur]
        self.locks = defaultdict(int)                    # (virage, roue) -> mesures
        self.spins = defaultdict(int)                    # virage -> mesures
        self.temps = [[0.0, 0.0, 0.0] for _ in range(4)]
        self.temps_n = 0
        self.bottom = 0
        self.bals = []
        self.over = defaultdict(int)            # virage -> mesures en surbraquage
        self.vmin = {}                          # virage -> vitesse mini sur ce tour
        self.bpeak = [0.0, 0.0]                 # pic de température des freins avant / arrière sur ce tour
        self.csteer = defaultdict(int)          # (virage, phase) -> mesures en contre-braquage (l'arrière décroche)
        self.dirty = False

    # ----------------------------------------------------------- virages
    def corner_at(self, f: float, ahead: float = 0.0) -> int | None:
        """Virage où l'on est (ou qui arrive dans `ahead` tour, pour les freinages)."""
        for c in self.map.corners():
            s, e = (c["start"] - ahead) % 1, c["end"] % 1
            inside = (s <= f < e) if s < e else (f >= s or f < e)
            if inside:
                return c["id"]
        return None

    # ----------------------------------------------------------- mesures
    def feed(self, m: dict | None) -> None:
        if not m:
            return
        with self.lock:
            if self._lap is None:
                self._lap = m["lap"]
            if m["lap"] != self._lap:
                if m["lap"] > self._lap:
                    self._end_lap()
                self._lap = m["lap"]
                self._new_lap()
            self._controls(m)
            if m["pits"]:
                self.dirty = True
                return
            if m["speed"] < MIN_SPEED:
                return
            f = m["f"]
            a = m["alpha"]
            # freinage : on rattache au virage qui arrive (zone de freinage avant le virage)
            bt = m.get("btemp")
            if bt:
                self.bpeak[0] = max(self.bpeak[0], bt[0], bt[1])
                self.bpeak[1] = max(self.bpeak[1], bt[2], bt[3])
            front_t = [sum(m["temps"][i]) / 3 for i in (0, 1)]
            cold = min(front_t) < COLD_TYRE or (bt is not None and max(bt[0], bt[1]) < COLD_BRAKE)
            if m["brk"] > 0.3 and not cold:              # pneus ou freins froids : un blocage ne veut rien dire
                c = self.corner_at(f, ahead=0.04)
                if c:
                    for i in range(4):
                        if m["ratio"][i] < LOCK:
                            self.locks[(c, i)] += 1
            if m["thr"] > 0.6:
                c = self.corner_at(f, ahead=0.0) or self.corner_at((f - 0.03) % 1)
                if c and max(m["ratio"][2], m["ratio"][3]) > SPIN:
                    self.spins[c] += 1
            if abs(m["lat"]) > CORNER_LAT:
                c = self.corner_at(f, ahead=0.02)
                # contre-braquage : le volant tourné à l'opposé du virage = l'arrière décroche. Le sens normal
                # (volant / accélération latérale) est appris sur la séance, pour ne pas dépendre des conventions du jeu.
                st = m.get("steer") or 0.0
                if abs(st) > 0.03:
                    sg = 1 if st * m["lat"] > 0 else -1
                    if abs(st) > 0.06 and abs(m["lat"]) > CORNER_LAT * 1.3:
                        self.sgn[sg] += 1
                    norm = 1 if self.sgn[1] >= self.sgn[-1] else -1
                    if c and sum(self.sgn.values()) > 300 and sg != norm:
                        ph = 0 if m["brk"] > 0.15 else 2 if m["thr"] > 0.5 else 1
                        self.csteer[(c, ph)] += 1
                if c:
                    self.vmin[c] = min(self.vmin.get(c, 999.0), m["speed"])
                    phase = 0 if m["brk"] > 0.15 else 2 if m["thr"] > 0.5 else 1
                    bal = (a[0] + a[1]) / 2 - (a[2] + a[3]) / 2
                    self.bals.append(bal)
                    if (a[0] + a[1]) / 2 > OVERDRIVE_ALPHA and bal > UNDER and m["thr"] < 0.3:
                        self.over[c] += 1
                    st = self.cur[(c, phase)]
                    st[0] += 1
                    if self.base is None:
                        st[1] += bal > UNDER
                        st[2] += bal < OVER
                    else:   # comparé à l'équilibre habituel de la voiture : on cherche les virages qui sortent du lot
                        st[1] += bal - self.base > REL
                        st[2] += bal - self.base < -REL
            # températures (en ligne droite, pneus stabilisés)
            if abs(m["lat"]) < 3 and m["speed"] > 30:
                for i in range(4):
                    for k in range(3):
                        self.temps[i][k] += m["temps"][i][k]
                self.temps_n += 1
                if min(m["ride"]) < 0.002:
                    self.bottom += 1

    # ----------------------------------------------------------- fin de tour
    def _controls(self, m: dict) -> None:
        """Repère quand tu changes un réglage dans la voiture (freins, TC, ABS, barres) et repart de zéro sur ce point."""
        now = time.monotonic()
        if m.get("pits") or m.get("speed", 0) < 20:
            self.ctrl_pending.clear()      # au garage / au stand LMU remet des valeurs à zéro : on ignore
            return
        if m.get("bias") and 0.2 < m["bias"] < 0.8:
            self.bias_front = (1 - m["bias"]) * 100
            if self.bias_start is None:
                self.bias_start = self.bias_front
        for k in ("bias", "tc", "abs"):
            v = m.get(k)
            if v is None or v == 0 or (k == "bias" and not 0.2 < v < 0.8):
                continue
            v = round(v, 4) if isinstance(v, float) else v
            if self.ctrl_track != self.map.track:
                self.ctrl, self.ctrl_pending = {}, {}
                self.ctrl_track = self.map.track
                self.bias_done, self.corner_v = False, {}
            old = self.ctrl.get(k)
            if old is None:
                self.ctrl[k] = v
                continue
            if v == old:
                self.ctrl_pending.pop(k, None)
                continue
            first = self.ctrl_pending.setdefault(k, (v, now))
            if first[0] != v:
                self.ctrl_pending[k] = (v, now)
            elif now - first[1] > 2.0:            # stable depuis 2 s : changement validé
                self.ctrl[k] = v
                self.ctrl_pending.pop(k, None)
                self._reset_linked(k)
                self.hold_until = self.laps_seen + HOLD_LAPS
                if k == "bias":
                    self.bias_done = True
                if self.say:
                    if k == "bias":
                        val = dec(L(f"à {(1 - v) * 100:.1f} % à l'avant", f"{(1 - v) * 100:.1f} % front"))
                    else:
                        val = L(f"sur {v}", f"{v}")
                    self.say(None, L(f"{CTRL_NAME[k]} {'passée' if k == 'bias' else 'passé'} {val}, je réévalue.", f"{CTRL_NAME_EN[k]} now {val}, re-evaluating."))

    def _reset_linked(self, k: str) -> None:
        links = LINKED.get(k, set())

        def linked(it):
            return any(it[0] == kind and (where is None or it[2] == where) for kind, where in links)

        for lap in self.history:
            for it in [x for x in lap if linked(x)]:
                lap.discard(it)
        for key in [x for x in self.repeats if linked(x)]:
            self.repeats.pop(key)
        for key in [x for x in self.group_said if any(x[0] == kind and (where is None or x[1] == where) for kind, where in links)]:
            self.group_said.pop(key)
        self.issues = [i for i in self.issues if not linked((i["kind"], i["corner"], i["where"]))]

    def _end_lap(self) -> None:
        self.laps_seen += 1
        if self.dirty:
            return
        found = set()
        for (c, ph), (n, u, o) in self.cur.items():
            if n < 3:
                continue
            if u / n > 0.4:
                found.add(("sous-virage", c, PHASES[ph]))
            elif o / n > 0.3:
                found.add(("survirage", c, PHASES[ph]))
        for (c, w), k in self.locks.items():
            if k >= 2:
                found.add(("blocage", c, "avant" if w < 2 else "arrière"))
        for c, v in self.vmin.items():
            self.corner_v[c] = v if c not in self.corner_v else 0.7 * self.corner_v[c] + 0.3 * v
        if min(self.bpeak) > 50:
            self.brake_hist.append(list(self.bpeak))
            self.brake_peaks = [sorted(x[i] for x in self.brake_hist)[len(self.brake_hist) // 2] for i in (0, 1)]
        for c, k in self.spins.items():
            if k >= 3:
                found.add(("patinage", c, ""))
        for (c, ph), k in self.csteer.items():
            if k >= 8:          # ~0,15 s de contre-braquage dans ce virage : l'arrière a décroché
                found.add(("survirage", c, PHASES[ph]))
        for c, k in self.over.items():
            if k >= 4:
                found.add(("surbraquage", c, ""))
        # équilibre général de la voiture sur ce tour
        if len(self.bals) > 30:
            b = sorted(self.bals)[len(self.bals) // 2]
            self.base_hist.append(b)
            self.base = sorted(self.base_hist)[len(self.base_hist) // 2]
            if b > GLOBAL_UNDER:
                found.add(("sous-virage", 0, "milieu"))
            elif b < GLOBAL_OVER:
                found.add(("survirage", 0, "milieu"))
        self.history.append(found)
        self._tyres()
        self._confirm()

    def _confirm(self) -> None:
        count = defaultdict(int)
        for lap in self.history:
            for it in lap:
                count[it] += 1
        confirmed = [it for it, k in count.items() if k >= 2]
        order = {"blocage": 0, "survirage": 1, "sous-virage": 2, "surbraquage": 3, "patinage": 4}
        confirmed.sort(key=lambda it: (order[it[0]], it[1]))
        self.group_n = defaultdict(int)          # (type, phase) -> nombre de virages touchés
        for k, c, w in confirmed:
            self.group_n[(k, w)] += 4 if c == 0 else 1
        self.issues = [{"kind": k, "corner": c, "where": w, "text": self.describe((k, c, w)), "tip": self.tip((k, c, w)),
                        "fast": self.fast(c), "n": self.group_n[(k, w)]}
                       for k, c, w in confirmed]
        if self.driver_issue and not any(i["kind"] == self.driver_issue["kind"] for i in self.issues):
            self.issues.append(dict(self.driver_issue))
        # annonces regroupées ("sous-virage au milieu des virages 4, 5 et 6"), au plus 1 tous les 3 tours
        import alerts   # niveau d'encouragements choisi : « motivant » parle plus souvent
        lvl = alerts.ENCOURAGE
        if not self.say or self.laps_seen - self.last_say < {"discret": 4, "normal": SAY_EVERY, "motivant": 2}[lvl]:
            return
        if self.laps_seen < self.hold_until:
            return       # un réglage vient de changer : on lui laisse 3 tours avant de juger
        groups = {}
        for k, c, w in confirmed:
            groups.setdefault((k, w), []).append(c)
        for (k, w), corners in groups.items():
            corners = sorted(corners)
            prev = self.group_said.get((k, w))
            new_corners = prev is None or not set(corners) <= set(prev[0])
            if self.repeats[(k, corners[0], w)] >= MAX_REPEAT and not new_corners:
                continue   # déjà dit 2 fois : on ne radote pas (toujours dispo si tu demandes)
            if new_corners or self.laps_seen - prev[1] >= (6 if lvl == "motivant" else 10):
                self.repeats[(k, corners[0], w)] += 1
                self.group_said[(k, w)] = (corners, self.laps_seen)
                self.last_say = self.laps_seen
                d = self.describe_group(k, w, corners)
                d = d[:1].upper() + d[1:]
                garage = _garage(k, w)
                if garage:
                    self.garage_notes[(k, w)] = f"{self.describe_group(k, w, corners)}{L(' : ', ': ')}{garage}"
                if _in_car(k, w):
                    tip = self.tip((k, corners[0], w), corners)
                    self.say(None, L(f"{d}. Conseil : {tip}.", f"{d}. Tip: {tip}."))
                else:
                    if self.repeats[(k, corners[0], w)] > 1:
                        continue   # problème de garage : dit une seule fois en piste
                    if time.monotonic() - self.garage_said < {"discret": 45, "normal": 20, "motivant": 10}[lvl] * 60:
                        continue   # une seule annonce « garage » par session : le reste est noté pour la fin
                    self.garage_said = time.monotonic()
                    self.say(None, L(f"{d}. Ça se corrige au garage, je te le rappelle après la course.",
                                     f"{d}. That's a garage fix, I'll remind you after the race."))
                break

    @staticmethod
    def describe_group(k: str, w: str, corners: list) -> str:
        if 0 in corners:
            return Behavior.describe((k, 0, w))
        if len(corners) == 1:
            return Behavior.describe((k, corners[0], w))
        lst = ", ".join(str(c) for c in corners[:-1]) + L(f" et {corners[-1]}", f" and {corners[-1]}")
        if k == "blocage":
            return L(f"blocage {w} au freinage des virages {lst}", f"{_wheel_en(w)} lock-up braking into turns {lst}")
        if k == "patinage":
            return L(f"patinage en sortie des virages {lst}", f"wheelspin on exit of turns {lst}")
        if k == "surbraquage":
            return L(f"trop d'angle de volant aux virages {lst}, l'avant glisse", f"too much steering at turns {lst}, the front is sliding")
        if w == "milieu":
            return L(f"{k} au milieu des virages {lst}", f"mid-corner {KIND_EN[k]} at turns {lst}")
        return L(f"{k} en {w} des virages {lst}", f"{KIND_EN[k]} on {PHASE_EN.get(w, w)} at turns {lst}")

    def _tyres(self) -> None:
        if self.temps_n < 20:
            return
        t = [[v / self.temps_n for v in w] for w in self.temps]
        findings = []   # version structurée, utilisée par l'atelier setup
        deltas = {}
        for i in range(4):
            outer, mid, inner = (t[i][0], t[i][1], t[i][2]) if i % 2 == 0 else (t[i][2], t[i][1], t[i][0])
            edges = (inner + outer) / 2
            if inner - outer > 12:
                findings.append(("camber_less", i)); deltas[("camber_less", i)] = inner - outer
            elif outer - inner > 6:
                findings.append(("camber_more", i))
            if mid - edges > 6:
                findings.append(("pressure_down", i))
            elif edges - mid > 6:
                findings.append(("pressure_up", i))
        self.tyre_findings = findings
        # texte : on regroupe avant / arrière quand les deux côtés disent la même chose
        TXT = {
            "camber_less": (L("plus chaud{s} à l'intérieur{d} : un peu moins de carrossage", "hotter on the inside{d}: a bit less camber")),
            "camber_more": (L("plus chaud{s} à l'extérieur : un peu plus de carrossage", "hotter on the outside: a bit more camber")),
            "pressure_down": (L("chaud{s} au centre : pression un peu trop haute", "hot in the middle: pressure a bit too high")),
            "pressure_up": (L("froid{s} au centre : pression un peu trop basse", "cold in the middle: pressure a bit too low")),
        }
        names = L("avant gauche|avant droit|arrière gauche|arrière droit", "front left|front right|rear left|rear right").split("|")
        merged, single = [], []
        done = set()
        for kind in TXT:
            for axle, (a, b) in ((L("avant", "front"), (0, 1)), (L("arrière", "rear"), (2, 3))):
                if (kind, a) in findings and (kind, b) in findings:
                    dd = max(deltas.get((kind, a), 0), deltas.get((kind, b), 0))
                    d = f" ({dd:.0f}°)" if dd else ""
                    merged.append(L(f"pneus {axle} ", f"{axle} tyres ") + TXT[kind].format(s="s", d=d))
                    done |= {(kind, a), (kind, b)}
        for kind, i in findings:
            if (kind, i) in done:
                continue
            dd = deltas.get((kind, i), 0)
            d = f" ({dd:.0f}°)" if dd else ""
            single.append(L(f"pneu {names[i]} ", f"{names[i]} tyre ") + TXT[kind].format(s="", d=d))
        self.tyre_tips = merged + single
        # pneus : seulement si le constat change, ou un rappel tous les 10 tours
        key = tuple(self.tyre_tips[:2])
        said, when = self.tyre_said
        if self.say and key and said is None and self.laps_seen - self.last_say >= 1:
            self.tyre_said = (key, self.laps_seen)
            self.say(None, L("Côté pneus : ", "Tyres: ") + " ; ".join(self.tyre_tips[:2])
                     + L(". C'est pour le garage, je te le rappelle après la course.", ". That's for the garage, I'll remind you after the race."))

    # ----------------------------------------------------------- textes
    @staticmethod
    def describe(it) -> str:
        k, c, w = it
        if c == 0:
            return (L("la voiture est globalement sous-vireuse", "the car is understeering overall") if k == "sous-virage"
                    else L("la voiture est globalement survireuse", "the car is oversteering overall"))
        if k == "blocage":
            return L(f"blocage {w} au freinage du virage {c}", f"{_wheel_en(w)} lock-up braking into turn {c}")
        if k == "patinage":
            return L(f"patinage en sortie du virage {c}", f"wheelspin on exit of turn {c}")
        if k == "surbraquage":
            return L(f"trop d'angle de volant au virage {c}, l'avant glisse", f"too much steering at turn {c}, the front is sliding")
        if w == "milieu":
            return L(f"{k} au milieu du virage {c}", f"mid-corner {KIND_EN[k]} at turn {c}")
        return L(f"{k} en {w} du virage {c}", f"{KIND_EN[k]} on {PHASE_EN.get(w, w)} of turn {c}")

    def fast(self, c: int) -> bool:
        """Virage rapide (vitesse mini habituelle au-dessus de ~150 km/h) : l'aéro y compte plus que la mécanique."""
        return self.corner_v.get(c, 0.0) > FAST_V

    def tip(self, it, corners: list | None = None) -> str:
        k, c, w = it
        b = self.bias_front
        if k == "blocage":
            front = "avant" in w
            n = len(corners) if corners else getattr(self, "group_n", {}).get((k, w), 1)
            if n <= LOCK_DRIVING:
                # un ou deux virages : zone de freinage bosselée, en descente, ou freinage trop appuyé. Pas de réglage.
                return L("c'est le pilotage plutôt que le réglage, freine un peu moins fort à l'attaque et relâche plus progressivement",
                         "that's driving rather than setup, brake a little less hard at the start and release more progressively")
            abs_now = self.ctrl.get("abs")
            if front and abs_now:
                a = int(round(abs_now))
                return L(f"monte l'ABS d'un cran, de {a} à {a + 1}", f"one more click of ABS, from {a} to {a + 1}")
            if not self.bias_done and b:
                nb = b - 0.5 if front else b + 0.5
                return dec(L(f"passe la répartition de freinage de {b:.1f} à {nb:.1f} % à l'avant",
                             f"move the brake bias from {b:.1f} to {nb:.1f} % front"))
            if front:
                return L("freine un peu moins fort à l'attaque ; au garage, baisse un peu la pression de freinage",
                         "brake a little less hard at the start; in the garage, lower the brake pressure a little")
            return L("au garage, un peu plus de blocage du différentiel au lever de pied pour stabiliser l'arrière",
                     "in the garage, a bit more diff coast lock to settle the rear")
        if k in ("patinage", "surbraquage"):
            return _tip(k, "")
        if (k, w) == ("sous-virage", "entrée") and self.bias_done:
            return L("au garage, barre antiroulis avant plus souple ; la répartition a déjà été réglée",
                     "in the garage, softer front anti-roll bar; the brake bias is already set")
        if (k, w) == ("survirage", "entrée") and self.bias_done:
            return L("au garage, un peu plus de blocage du différentiel au lever de pied ; la répartition a déjà été réglée",
                     "in the garage, a bit more diff coast lock; the brake bias is already set")
        if (k, w) == ("sous-virage", "entrée"):
            return dec(L(f"recule la répartition de freinage de {b:.1f} à {b - 0.5:.1f} % à l'avant",
                         f"move the brake bias back from {b:.1f} to {b - 0.5:.1f} % front") if b else
                       L("recule un peu la répartition de freinage", "move the brake bias back a little"))
        if (k, w) == ("survirage", "entrée"):
            return dec(L(f"avance la répartition de freinage de {b:.1f} à {b + 0.5:.1f} % à l'avant",
                         f"move the brake bias forward from {b:.1f} to {b + 0.5:.1f} % front") if b else
                       L("avance un peu la répartition de freinage", "move the brake bias forward a little"))
        if (k, w) == ("survirage", "sortie"):
            return L("monte le contrôle de traction d'un cran, et dose l'accélération en sortie",
                     "one more click of traction control, and be smoother on exit")
        if not _in_car(k, w):
            return _garage(k, w) or _tip(k, w)
        return _tip(k, w)

    def end_of_session(self) -> str | None:
        """Résumé des changements à faire au garage, dit une fois la session terminée."""
        with self.lock:
            notes = list(self.garage_notes.values())
            for i in self.issues:
                g = _garage(i["kind"], i["where"])
                if g and not any(i["text"] in n for n in notes):
                    notes.append(f"{i['text']}{L(' : ', ': ')}{g}")
            notes += self.tyre_tips[:2]
        if not notes:
            return None
        return L("Pour le setup, voici ce que je changerais : ", "For the setup, here's what I'd change: ") + " ; ".join(notes[:4]) \
            + L(". J'ouvre l'atelier setup avec mes propositions.", ". I'm opening the setup workshop with my suggestions.")

    def driver_report(self, kind: str) -> str:
        """Le pilote dit ce qu'il ressent (« l'arrière glisse », « elle ne tourne pas ») : on le note et on conseille,
        même si les mesures ne le montrent pas encore. Repris dans les propositions de setup."""
        with self.lock:
            seen = [i for i in self.issues if i["kind"] == kind and not i.get("driver")]
            w = "milieu"
            if kind == "survirage":
                txt = L("arrière instable, signalé par toi", "unstable rear, reported by you")
                tip_now = L("un cran de contrôle de traction en plus, freine un peu plus tôt pour arriver moins vite en entrée, et accélère plus progressivement",
                            "one more click of traction control, brake a bit earlier to carry less entry speed, and be smoother on the throttle")
            else:
                txt = L("sous-virage, signalé par toi", "understeer, reported by you")
                tip_now = L("freine un peu plus tôt et en ligne droite, attends que l'avant morde avant de remettre les gaz",
                            "brake a bit earlier and in a straight line, wait for the front to bite before getting on the throttle")
            garage = _garage(kind, w)
            self.driver_issue = {"kind": kind, "corner": 0, "where": w, "text": txt, "tip": tip_now,
                                 "fast": False, "n": 4, "driver": True}
            self.issues = [i for i in self.issues if not i.get("driver")]
            if not any(i["kind"] == kind for i in self.issues):
                self.issues.append(dict(self.driver_issue))
            for k in [k for k in self.garage_notes if isinstance(k, tuple) and k[0] == "pilote"]:
                del self.garage_notes[k]
            self.garage_notes[("pilote", kind)] = f"{txt}{L(' : ', ': ')}{garage}" if garage else txt
        if seen:
            where = ", ".join(sorted({str(i["corner"]) for i in seen if i["corner"]}))
            head = L(f"Bien reçu, je le vois aussi dans les mesures{(' : virages ' + where) if where else ''}. ",
                     f"Copy, I see it in the data too{(' : turns ' + where) if where else ''}. ")
        else:
            head = L("Bien reçu, je te crois : les mesures ne le montrent pas encore clairement, je le note et je surveille. ",
                     "Copy, I believe you: the data doesn't show it clearly yet, I'm noting it and watching. ")
        tail = L(f" Au garage, je proposerai : {garage}." if garage else "", f" In the garage I'll suggest: {garage}." if garage else "")
        return head + L("En attendant : ", "Meanwhile: ") + tip_now + "." + tail

    def summary(self) -> str:
        with self.lock:
            if not self.map.corners():
                return L("J'ai besoin d'un tour complet pour connaître le circuit avant d'analyser la voiture.",
                         "I need a full lap to learn the track before analysing the car.")
            if self.laps_seen < 3:
                return L("J'analyse encore, il me faut deux ou trois tours propres.", "Still analysing, I need two or three clean laps.")
            out = []
            if self.issues:
                out.append(L(" ; ", "; ").join(f"{i['text']}{L(' : ', ': ')}{i['tip']}" for i in self.issues[:3]) + ".")
            else:
                out.append(L("La voiture est plutôt équilibrée, rien de répétitif à signaler.", "The car is fairly balanced, nothing recurring to report."))
            if self.tyre_tips:
                out.append(L("Pneus : ", "Tyres: ") + " ; ".join(self.tyre_tips[:2]) + ".")
            txt = " ".join(out)
            return txt[:1].upper() + txt[1:]

    def ui(self) -> dict:
        with self.lock:
            corners = self.map.corners()
            by = {}
            for it in self.issues:
                by.setdefault(it["corner"], it["kind"])
            return {"corners": [{"id": c["id"], "x": c["x"], "z": c["z"], "issue": by.get(c["id"])} for c in corners],
                    "issues": self.issues[:4], "tyres": self.tyre_tips[:3], "laps": self.laps_seen}
