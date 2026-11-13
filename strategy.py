"""
Moteur de stratégie : transforme les données de course en décisions d'ingénieur.

- consommation d'essence et d'énergie virtuelle par tour (sur les tours "propres")
- autonomie, tours restants jusqu'à l'arrivée, nombre d'arrêts
- tour d'arrêt, quantité d'essence / énergie à remettre, pneus à changer ou non
- annonces radio (texte pour l'instant, la voix viendra ensuite)
"""

from __future__ import annotations

import math
import random
import statistics
from collections import deque
from dataclasses import dataclass, field

from telemetry import Snapshot
from i18n import L, dec
from phrases import pick, dress

MARGIN_LAPS = 0.5        # marge de sécurité en tours d'essence / énergie (quantité à mettre, arrêts nécessaires)
BOX_RESERVE = 0.2        # réserve gardée en arrivant au stand : on roule jusqu'au dernier tour possible
TYRE_LIMIT = 0.30        # on considère un pneu à changer sous 30 % restant
AVG_OVER = 5             # moyenne sur les 5 derniers tours propres


@dataclass
class Plan:
    ready: bool = False                 # assez de tours pour calculer
    fuel_per_lap: float | None = None
    energy_per_lap: float | None = None
    avg_lap: float | None = None
    laps_to_finish: float | None = None
    range_laps: float | None = None     # autonomie (min essence / énergie)
    limited_by: str = ""                # "essence" ou "énergie"
    stops_needed: int | None = None
    box_lap: int | None = None          # rentrer à la fin de ce tour
    laps_until_box: int | None = None
    fuel_to_add: float | None = None
    energy_target: float | None = None  # niveau d'énergie à viser au stand (0..1)
    change_tyres: bool | None = None
    tyre_compound: str = ""             # "pluie" / "slicks" / ""
    tyre_laps_left: float | None = None
    save_per_lap: float | None = None   # litres à économiser par tour pour éviter un arrêt
    weather: str = ""
    repair: bool = False                # réparations à faire au prochain arrêt
    no_repair: bool = False             # le pilote a dit « pas de réparation »
    repair_all: bool = False            # « Tout réparer » (mécanique) plutôt que « Réparer la carrosserie »
    fuel_total: float | None = None     # niveau d'essence voulu après l'arrêt (menu des stands LMU)


@dataclass
class _Lap:
    number: int
    fuel: float
    energy: float | None
    wear: list
    time: float | None = None
    dirty: bool = False  # passage aux stands ou neutralisation pendant le tour


class Engineer:
    def __init__(self) -> None:
        self.laps: list[_Lap] = []
        self.current: _Lap | None = None
        self.radio: deque = deque(maxlen=40)
        self._said: set[str] = set()
        self._last_stops = 0
        self._was_yellow = False
        self._was_wet = False
        self._session_key = None
        self._stop_lap = None
        self.plan = Plan()
        self.on_say = None  # fonction appelée pour dire le message à voix haute

    # ------------------------------------------------------------------ radio
    def say(self, key: str | None, text: str, urgent: bool = False, elapsed: float = 0.0) -> None:
        if key is not None:
            if key in self._said:
                return
            self._said.add(key)
        text = dress(text, urgent=urgent)
        self.radio.appendleft({"t": elapsed, "text": text, "urgent": urgent})
        if self.on_say:
            self.on_say(text, urgent)

    # ----------------------------------------------------------- historique
    def _reset(self) -> None:
        self.laps.clear()
        self.current = None
        self._said.clear()
        self._last_stops = 0
        self._stop_lap = None
        self.plan = Plan()

    def _track_laps(self, s: Snapshot) -> None:
        key = (s.track, s.car, s.session)
        if key != self._session_key or (self.current and s.laps_done < self.current.number):
            self._session_key = key
            self._reset()

        if self.current is None or s.laps_done != self.current.number:
            if self.current is not None:
                self.current.time = s.last_lap
                self.laps.append(self.current)
            self.current = _Lap(s.laps_done, s.fuel, s.energy, list(s.tyre_wear))
        if s.in_pits or s.yellow:
            self.current.dirty = True

    def _per_lap(self, attr: str, safe: bool = False) -> float | None:
        """Consommation par tour. safe=True : valeur prudente (3e quartile) pour la quantité à mettre au stand."""
        vals = []
        for a, b in zip(self.laps, self.laps[1:] + [self.current]):
            if a.dirty or a.number == 0 or b is None:
                continue
            va, vb = getattr(a, attr), getattr(b, attr)
            if va is None or vb is None:
                continue
            d = va - vb
            if d > 0:
                vals.append(d)
        vals = vals[-AVG_OVER:]
        if not vals:
            return None
        if safe:
            return max(vals) if len(vals) < 4 else statistics.quantiles(vals, n=4)[2]
        return statistics.median(vals)

    @staticmethod
    def _race_end(s: Snapshot, avg: float) -> float:
        """Course au temps : secondes jusqu'à la fin pour TOI. À 0:00, la course ne s'arrête pas :
        le 1er (toutes catégories) finit son tour, puis tu finis le tien. Sans ça, on oublie souvent un tour."""
        leader = next((c for c in s.cars if c.get("p") == 1), None)
        if leader is None or leader.get("me"):
            lead_f, lead_lap = s.lap_frac, avg
        else:
            lead_f = leader.get("f") or 0.0
            lead_lap = (leader.get("best") or avg) * 1.03       # rythme de course ≈ meilleur tour + 3 %
        frac_at_zero = (lead_f + s.time_left / lead_lap) % 1.0  # où sera le 1er quand le chrono tombe à 0
        return s.time_left + (1.0 - frac_at_zero) * lead_lap

    def _avg_lap(self) -> float | None:
        times = [l.time for l in self.laps if l.time and not l.dirty and l.number > 0][-AVG_OVER:]
        return statistics.median(times) if times else None

    def _wear_rate(self) -> float | None:
        rates = []
        for a, b in zip(self.laps, self.laps[1:] + [self.current]):
            if a.dirty or b is None:
                continue
            d = max(wa - wb for wa, wb in zip(a.wear, b.wear))
            if d > 0:
                rates.append(d)
        rates = rates[-AVG_OVER:]
        return statistics.median(rates) if rates else None

    # ------------------------------------------------------------ calcul
    def update(self, s: Snapshot) -> Plan:
        if not s.on_track:
            return self.plan
        self._track_laps(s)
        et = s.elapsed
        p = Plan()
        p.repair = s.repair
        p.no_repair = s.no_repair
        p.repair_all = s.repair_all

        # nouveau relais après un arrêt
        if s.pit_stops != self._last_stops:
            self._last_stops = s.pit_stops
            self._stop_lap = s.laps_done
            self._said = {k for k in self._said if k.startswith("once:")}

        fpl = self._per_lap("fuel")
        epl = self._per_lap("energy") if s.energy is not None else None
        avg = self._avg_lap() or s.last_lap or s.best_lap
        p.fuel_per_lap, p.energy_per_lap, p.avg_lap = fpl, epl, avg

        # tours jusqu'à l'arrivée (depuis la position actuelle)
        if s.max_laps:
            p.laps_to_finish = max(0.0, s.max_laps - s.laps_done - s.lap_frac)
        elif s.time_left is not None and avg:
            p.laps_to_finish = math.ceil(s.lap_frac + self._race_end(s, avg) / avg) - s.lap_frac

        self._weather(s, p)
        self._flags(s)

        if not fpl or p.laps_to_finish is None or s.session != "course":
            self.plan = p
            return p
        p.ready = True

        fuel_range = s.fuel / fpl
        energy_range = (s.energy / epl) if (epl and s.energy is not None) else math.inf
        p.range_laps = min(fuel_range, energy_range)
        p.limited_by = "énergie" if energy_range < fuel_range else "essence"

        full_stint = min(s.fuel_capacity / fpl if s.fuel_capacity else math.inf, (1.0 / epl) if epl else math.inf)
        short = p.laps_to_finish + MARGIN_LAPS - p.range_laps
        p.stops_needed = 0 if short <= 0 else math.ceil(short / max(full_stint - MARGIN_LAPS, 1.0))

        # tyres
        wr = self._wear_rate()
        if wr:
            p.tyre_laps_left = max(0.0, (min(s.tyre_wear) - TYRE_LIMIT) / wr)

        if s.pit_stops and self._stop_lap is not None and s.laps_done - self._stop_lap < 2:
            self.plan = p          # juste après l'arrêt : on attend un tour propre avant de parler essence
            return p
        # il manque moins d'un demi-tour d'essence (sans la marge) : un arrêt coûterait bien plus cher
        # que de lever un peu le pied. On ne rentre pas, on économise.
        real_short = p.laps_to_finish - p.range_laps
        if p.stops_needed == 1 and p.limited_by == "essence" and real_short < 0.5 and p.laps_to_finish >= 1.5:
            p.stops_needed = 0
            p.save_per_lap = max(0.1, (max(real_short, 0.0) + 0.2) * fpl / max(p.laps_to_finish, 1))
            q = dec(f"{p.save_per_lap:.1f}")
            self.say("stint:tight", pick("tight", [
                (f"C'est juste en essence, mais on ne s'arrête pas. Économise environ {q} litre par tour.",
                 f"Fuel is tight, but we're not stopping. Save about {q} litres a lap."),
                (f"On va au bout sans s'arrêter, mais il faut gratter {q} litre par tour. Lève un peu plus tôt avant les freinages.",
                 f"We go to the end without stopping, but find {q} litres a lap. Lift a bit earlier before braking."),
                (f"Pas d'arrêt : un passage au stand coûterait trop cher. Gagne juste {q} litre par tour.",
                 f"No stop: pitting would cost too much. Just save {q} litres a lap.")]), elapsed=et)
            self.plan = p
            return p
        if p.stops_needed == 0:
            self.say("once:enough", pick("enough", [
                ("Tu as ce qu'il faut pour aller au bout, pas besoin de rentrer.", "You've got enough to make the finish, no need to pit."),
                ("Bonne nouvelle : l'essence suffit jusqu'à l'arrivée, on ne s'arrête plus.", "Good news: fuel's fine to the end, no more stops."),
                ("C'est bon pour l'essence, on va au bout sans rentrer.", "Fuel is good, we go to the end without pitting."),
                ("Plus d'arrêt prévu, tu as assez pour finir. Concentre-toi sur le pilotage.", "No more stops, you've got enough to finish. Just drive.")]), elapsed=et)
            self.plan = p
            return p

        # économie possible pour éviter l'arrêt ?
        if p.stops_needed == 1 and short < 1.2 and p.limited_by == "essence":
            p.save_per_lap = short * fpl / max(p.laps_to_finish, 1)
        if p.save_per_lap and 0.1 <= p.save_per_lap <= 0.15 * fpl and p.laps_to_finish >= 3:
            q = dec(f"{p.save_per_lap:.1f}")
            self.say("stint:save", pick("save", [
                (f"Il manque un peu d'essence pour finir. Si tu économises {q} litre par tour, on évite l'arrêt.",
                 f"We're a little short on fuel. Save {q} litres a lap and we can skip the stop."),
                (f"On est juste en essence. Gagne {q} litre par tour et on va au bout sans s'arrêter.",
                 f"Fuel is tight. Find {q} litres a lap and we go to the end without stopping."),
                (f"Mode économie : {q} litre par tour à gagner, lève un peu plus tôt avant les freinages, et l'arrêt saute.",
                 f"Fuel save mode: {q} litres a lap, lift a bit earlier before braking, and we skip the stop."),
                (f"Si tu veux éviter l'arrêt, il faut {q} litre de moins par tour. Lift and coast, c'est jouable.",
                 f"To skip the stop we need {q} litres less a lap. Lift and coast, it's doable.")]), elapsed=et)

        # tour d'arrêt
        k = math.floor(s.lap_frac + p.range_laps - BOX_RESERVE)
        p.laps_until_box = max(0, k)
        p.box_lap = s.laps_done + max(1, k)

        # quantités au stand
        laps_driven_before = max(0.0, max(1, k) - s.lap_frac)
        laps_after = max(0.0, p.laps_to_finish - laps_driven_before)
        fpl_safe = self._per_lap("fuel", safe=True) or fpl    # prudent : mieux vaut 1 litre de trop qu'un tour de moins
        fuel_at_pit = max(0.0, s.fuel - laps_driven_before * fpl_safe)
        if p.stops_needed == 1:
            need = (laps_after + MARGIN_LAPS) * fpl_safe - fuel_at_pit
        else:
            need = s.fuel_capacity - fuel_at_pit
        room = (s.fuel_capacity - fuel_at_pit) if s.fuel_capacity else need
        p.fuel_to_add = max(0.0, min(need, room))
        p.fuel_total = min(s.fuel_capacity or 999, fuel_at_pit + p.fuel_to_add)
        if epl and s.energy is not None:
            p.energy_target = 1.0 if p.stops_needed > 1 else min(1.0, (laps_after + MARGIN_LAPS) * epl)

        stint_after = min(laps_after, full_stint)
        if p.tyre_compound:
            p.change_tyres = True
        elif p.tyre_laps_left is not None:
            p.change_tyres = (p.tyre_laps_left - laps_driven_before) < stint_after
        else:
            p.change_tyres = None

        self._pit_calls(s, p)
        self.plan = p
        return p

    # --------------------------------------------------------------- annonces
    def _pit_service(self, p: Plan) -> str:
        parts = []
        if p.fuel_to_add is not None:
            n = round(p.fuel_to_add)
            parts.append(L(f"{n} litre{'s' if n > 1 else ''}", f"{n} litre{'s' if n != 1 else ''} of fuel"))
        if p.energy_target is not None:
            parts.append(L(f"énergie à {p.energy_target * 100:.0f} %", f"energy to {p.energy_target * 100:.0f} %"))
        if p.tyre_compound == "pluie":
            parts.append(L("pneus pluie", "wet tyres"))
        elif p.tyre_compound == "slicks":
            parts.append(L("retour en slicks", "back to slicks"))
        elif p.change_tyres:
            parts.append(L("4 pneus neufs", "four new tyres"))
        elif p.change_tyres is False:
            parts.append(L("on garde les pneus", "we keep the tyres"))
        if p.repair:
            parts.append(L("et on répare tout", "and full repairs") if p.repair_all else L("et on répare la carrosserie", "and we fix the bodywork"))
        elif p.no_repair:
            parts.append(L("et on ne répare pas", "and no repairs"))
        return ", ".join(parts)

    def _pit_calls(self, s: Snapshot, p: Plan) -> None:
        et = s.elapsed
        if p.laps_until_box is None or s.in_pits or s.game_phase == 8:   # 8 = drapeau à damier : plus d'arrêt
            return
        if p.laps_until_box <= 1:
            sv = self._pit_service(p)
            self.say("stint:box", pick("box", [
                (f"Box, box ce tour ! On met {sv}.", f"Box, box this lap! {sv}."),
                (f"Tu rentres à la fin de ce tour, box box ! On met {sv}.", f"Pit at the end of this lap, box box! {sv}."),
                (f"Box box box ! L'équipe est prête : {sv}.", f"Box box box! The crew is ready: {sv}."),
                (f"Ce tour, c'est le bon : box, box ! Au programme, {sv}.", f"This is the lap: box, box! On the list, {sv}."),
                (f"Box cette fois ! Attention à la limite de vitesse dans la voie des stands. On met {sv}.",
                 f"Box this time! Watch the pit speed limit. {sv}.")]), urgent=True, elapsed=et)
        elif p.laps_until_box <= 3:
            n, sv = p.laps_until_box, self._pit_service(p)
            self.say("stint:box3", pick("box3", [
                (f"Arrêt dans {n} tours. Prévu : {sv}.", f"Pit stop in {n} laps. Plan: {sv}."),
                (f"On s'arrête dans {n} tours. L'équipe prépare {sv}.", f"We stop in {n} laps. The crew is getting {sv} ready."),
                (f"Encore {n} tours et on rentre. Au menu : {sv}.", f"{n} more laps and we pit. On the menu: {sv}."),
                (f"Prépare-toi, box dans {n} tours. On met {sv}.", f"Get ready, box in {n} laps. {sv}.")]), elapsed=et)
        if not ("stint:plan" in self._said):
            lim = L("l'énergie", "energy") if p.limited_by == "énergie" else L("l'essence", "fuel")
            c, r, k = f"{p.fuel_per_lap:.1f}", f"{p.range_laps:.1f}", p.stops_needed
            st_fr, st_en = f"{k} arrêt{'s' if k > 1 else ''}", f"{k} stop{'s' if k > 1 else ''}"
            self.say("stint:plan", pick("plan", [
                (f"Conso {c} litres par tour. Autonomie {r} tours, c'est {lim} qui limite. Il faudra {st_fr}.",
                 f"Using {c} litres a lap. Range {r} laps, {lim} is the limit. We need {st_en}."),
                (f"Point stratégie : tu consommes {c} litres au tour, ça fait {r} tours d'autonomie. On part sur {st_fr}, c'est {lim} qui décide.",
                 f"Strategy update: {c} litres a lap, that's {r} laps of range. We're on {st_en}, {lim} decides."),
                (f"Le plan : {st_fr}. Tu tiens {r} tours avec ce que tu as, à {c} litres par tour. C'est {lim} qui limite.",
                 f"The plan: {st_en}. You can do {r} laps on what you've got, at {c} litres a lap. {lim} is the limit.")]),
                     elapsed=et)

    def _weather(self, s: Snapshot, p: Plan) -> None:
        et = s.elapsed
        wet = s.wetness > 0.35 or s.raining > 0.3
        dry = s.wetness < 0.12 and s.raining < 0.05
        if s.raining > 0.1 and not self._was_wet:
            self.say(None, pick("rain", [
                ("Il commence à pleuvoir, attention à l'adhérence.", "It's starting to rain, watch the grip."),
                ("Quelques gouttes sur le circuit, sois doux sur les gaz.", "Some drops on track, be gentle on the throttle."),
                ("La pluie arrive. Freine un peu plus tôt et méfie-toi des vibreurs.", "Rain's coming. Brake a bit earlier and watch the kerbs."),
                ("Ça commence à mouiller, garde de la marge.", "It's getting wet out there, keep some margin.")]), elapsed=et)
            self._was_wet = True
        if dry:
            self._was_wet = False
        running = s.game_phase == 5 and not s.in_pits and s.laps_done >= 1
        if not running:
            p.weather = L(f"Pluie {s.raining * 100:.0f} %", f"Rain {s.raining * 100:.0f} %") if s.raining > 0.05 else L("Sec", "Dry")
            return
        if wet and not s.wet_tyres:
            p.tyre_compound = "pluie"
            p.weather = L("Piste mouillée — pneus pluie conseillés", "Wet track — wets recommended")
            self.say("stint:wets", pick("wets", [
                ("La piste est bien mouillée, on passe en pneus pluie au prochain arrêt.", "Track's properly wet, we go to wets at the next stop."),
                ("Ça devient trop mouillé pour les slicks. Pneus pluie au prochain arrêt.", "Too wet for slicks now. Wets at the next stop."),
                ("On change de plan : pneus pluie au prochain passage au stand.", "Change of plan: wets at the next stop.")]), elapsed=et)
        elif dry and s.wet_tyres:
            p.tyre_compound = "slicks"
            p.weather = L("Piste sèche — repasser en slicks", "Drying track — back to slicks")
            self.say("stint:slicks", pick("slicks", [
                ("La piste sèche, on repasse en slicks au prochain arrêt.", "Track is drying, back to slicks at the next stop."),
                ("Une trajectoire sèche apparaît. Slicks au prochain arrêt.", "A dry line is coming. Slicks at the next stop."),
                ("Ça sèche bien. On remet les slicks au prochain passage.", "It's drying nicely. Slicks back on at the next stop.")]), elapsed=et)
        elif s.raining > 0.05:
            p.weather = L(f"Pluie {s.raining * 100:.0f} %, piste humide à {s.wetness * 100:.0f} %",
                          f"Rain {s.raining * 100:.0f} %, track {s.wetness * 100:.0f} % wet")
        else:
            p.weather = L("Sec", "Dry")

    def _flags(self, s: Snapshot) -> None:
        if s.yellow and not self._was_yellow:
            self.say(None, pick("yellow", [
                ("Drapeau jaune ! Ralentis.", "Full course yellow! Slow down."),
                ("Drapeau jaune sur tout le circuit, on ralentit !", "Full course yellow, slow it down!"),
                ("Drapeau jaune ! Pas de dépassement, on lève le pied.", "Full course yellow! No overtaking, ease off.")]), urgent=True, elapsed=s.elapsed)
        if not s.yellow and self._was_yellow:
            self.say(None, pick("green", [
                ("Fin du drapeau jaune, la course reprend.", "Yellow's over, we're racing again."),
                ("Vert, vert, vert ! On repart à l'attaque.", "Green, green, green! Back to racing."),
                ("C'est reparti, la piste est libre. Remets les pneus en température.", "We're back on, track is clear. Get the heat back in the tyres.")]), elapsed=s.elapsed)
        self._was_yellow = s.yellow
        if s.done:
            self.say("once:finish", pick("finish", [
                ("Drapeau à damier ! Bien joué.", "Chequered flag! Well done."),
                ("Et c'est le drapeau à damier ! Superbe course, merci pour le boulot.", "And that's the chequered flag! Great race, thanks for the work."),
                ("Damier ! Course terminée, bravo. Tour de décélération tranquille.", "Chequered flag! Race done, well driven. Easy on the cool-down lap."),
                ("C'est fini ! Beau travail, toute l'équipe est contente.", "That's it! Great job, the whole team is happy.")]), elapsed=s.elapsed)
