"""
Lecture des données de Le Mans Ultimate (mémoire partagée native "LMU_Data").

Deux sources possibles :
- LMUSource  : lit le jeu en direct (Windows, LMU lancé).
- DemoSource : simule une course pour tester sans le jeu.

Les deux renvoient un objet Snapshot avec les mêmes champs.
"""

from __future__ import annotations

import math
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "vendor"))

WHEELS = ("AVG", "AVD", "ARG", "ARD")  # avant gauche, avant droit, arrière gauche, arrière droit


@dataclass
class Snapshot:
    connected: bool = False          # le jeu est-il lancé
    on_track: bool = False           # le joueur est-il dans une voiture
    track: str = ""
    car: str = ""
    car_class: str = ""
    session: str = ""                # "course", "qualif", "essais", "warmup"
    game_phase: int = 0              # 5 = vert, 6 = FCY/SC, 7 = arrêtée, 8 = terminée (le 1er a fini)
    finish_status: int = 0           # pour TA voiture : 0 = en course, 1 = arrivée, 2 = abandon, 3 = disqualifié
    time_left: float | None = None   # secondes restantes (course au temps)
    max_laps: int | None = None      # course au nombre de tours
    elapsed: float = 0.0
    laps_done: int = 0
    lap_frac: float = 0.0            # progression dans le tour en cours (0..1)
    last_lap: float | None = None
    best_lap: float | None = None
    position: int = 0
    class_position: int = 0
    num_cars: int = 0
    gap_ahead: float | None = None
    gap_behind: float | None = None
    fuel: float = 0.0                # litres
    fuel_capacity: float = 0.0
    energy: float | None = None      # énergie virtuelle 0..1 (Hypercar / LMGT3), None si absente
    tyre_wear: list = field(default_factory=lambda: [1.0] * 4)   # 1.0 = neuf
    tyre_temp: list = field(default_factory=lambda: [0.0] * 4)   # °C (couche intérieure de la gomme)
    tyre_surface_temp: list = field(default_factory=lambda: [0.0] * 4)   # °C (surface, varie très vite)
    tyre_opt: float = 0.0                                        # température idéale des pneus (°C)
    brake_temp: list = field(default_factory=lambda: [0.0] * 4)  # °C
    tyre_pressure: list = field(default_factory=lambda: [0.0] * 4)  # kPa
    compound: str = ""
    wet_tyres: bool = False
    in_pits: bool = False
    pit_state: int = 0               # 0 rien, 1 demandé, 2 entrée, 3 arrêté, 4 sortie
    pit_stops: int = 0
    raining: float = 0.0             # 0..1
    wetness: float = 0.0             # humidité moyenne de la piste 0..1
    air_temp: float = 0.0
    track_temp: float = 0.0
    yellow: bool = False
    lap_invalid: bool = False        # tour en cours invalidé (limites de piste…)
    sectors: list | None = None      # [S1, S2, S3] du dernier tour
    ahead: dict | None = None        # voiture devant dans ta catégorie
    behind: dict | None = None       # voiture derrière dans ta catégorie
    cars: list = field(default_factory=list)  # toutes les voitures, pour la carte
    rivals: list = field(default_factory=list)  # les autres voitures de ta catégorie (place, cpos, gap, tours…)
    session_code: int = 0            # code LMU de la session (0-13)
    track_len: float = 0.0           # longueur du tour (m)
    tl_steps: int = 0                # limites de piste : avertissements cumulés
    tl_per_penalty: int = 0          # ... avant pénalité
    dents: list = field(default_factory=lambda: [0] * 8)   # dégâts carrosserie (0, 1, 2) sur 8 zones
    flat: list = field(default_factory=lambda: [False] * 4)
    wheel_off: list = field(default_factory=lambda: [False] * 4)
    part_off: bool = False           # une pièce s'est détachée
    repair: bool = False             # réparation conseillée au prochain arrêt (rempli par les alertes)
    no_repair: bool = False          # le pilote a demandé de ne pas réparer
    repair_all: bool = False         # mécanique touchée (suspension, roue) : « Tout réparer » plutôt que la carrosserie
    gap_class_ahead: float | None = None    # écart (s) avec la voiture devant dans ta catégorie
    gap_class_behind: float | None = None
    driver: str = ""
    lap_time: float | None = None    # temps écoulé dans le tour en cours (s)
    penalties: int = 0               # pénalités à purger (drive-through / stop-go)

    @property
    def done(self) -> bool:
        """TU as fini ta session (en course : quand toi tu passes le drapeau, pas le 1er)."""
        if self.session == "course":
            return self.finish_status >= 1
        return self.game_phase == 8 or self.finish_status >= 1


def sector_index(m_sector: int) -> int:
    """LMU : 1 = secteur 1, 2 = secteur 2, 0 = secteur 3  ->  0, 1, 2."""
    return (m_sector + 2) % 3


def split_sectors(s1: float, s12: float, lap: float) -> list | None:
    """LMU donne S1, S1+S2 et le tour complet : on en tire les 3 secteurs."""
    if s1 > 0 and s12 > s1 and lap > s12:
        return [s1, s12 - s1, lap - s12]
    return None


def dynamics_sample(tel, sc, info) -> dict:
    v = tel.mLocalVel
    speed = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
    alpha, ratio, temps = [], [], []
    for w in tel.mWheels:
        lg = abs(w.mLongitudinalGroundVel)
        alpha.append(math.atan2(abs(w.mLateralGroundVel), max(lg, 1.0)))
        radius = (w.mStaticUndeflectedRadius or 33) / 100
        ratio.append((abs(w.mRotation) * radius - lg) / max(lg, 1.0))
    return {
        "lap": sc.mTotalLaps, "f": (sc.mLapDist / info.mLapDist) if info.mLapDist > 0 else 0.0,
        "pits": bool(sc.mInPits), "speed": speed, "lat": tel.mLocalAccel.x,
        "steer": tel.mUnfilteredSteering, "thr": tel.mUnfilteredThrottle, "brk": tel.mUnfilteredBrake,
        "alpha": alpha, "ratio": ratio,
        "temps": [[t - 273.15 for t in w.mTemperature] for w in tel.mWheels],
        "opt": tel.mWheels[0].mOptimalTemp, "ride": [tel.mFrontRideHeight, tel.mRearRideHeight],
        "tc": tel.mTC, "abs": tel.mABS, "bias": tel.mRearBrakeBias,
        "farb": tel.mFrontAntiSway, "rarb": tel.mRearAntiSway,
    }


def _txt(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("utf-8", "replace").strip()


def _session_name(code: int) -> str:
    if code >= 10:
        return "course"
    if code == 9:
        return "warmup"
    if code >= 5:
        return "qualif"
    return "essais"


class LMUSource:
    """Lecture en direct de la mémoire partagée de LMU."""

    def __init__(self) -> None:
        from pyLMUSharedMemory import lmu_data, lmu_mmap

        self._mm = lmu_mmap.MMapControl(lmu_data.LMUConstants.LMU_SHARED_MEMORY_FILE, lmu_data.LMUObjectOut)
        self._mm.create(0)  # copie : évite les données à moitié écrites
        # 2e accès, direct (sans copie), pour la lecture rapide de la dynamique
        self._fast = lmu_mmap.MMapControl(lmu_data.LMUConstants.LMU_SHARED_MEMORY_FILE, lmu_data.LMUObjectOut)
        self._fast.create(1)
        self._player_sc = 0
        self._alive_t = 0.0   # dernière fois où l'interface web de LMU (port 6397) a répondu
        self._probe_t = 0.0
        self._last_et = None  # temps de séance : s'il avance, le jeu tourne

    def _game_alive(self, et: float | None = None) -> bool:
        """La mémoire partagée garde les dernières données après la fermeture du jeu :
        on vérifie aussi que LMU répond encore sur son port local (6397)."""
        now = time.time()
        if et is not None and et != self._last_et:
            if self._last_et is not None:
                self._alive_t = now   # secours si le port est bloqué : la séance avance
            self._last_et = et
        if now - self._probe_t > 3:
            self._probe_t = now
            try:
                import socket
                socket.create_connection(("127.0.0.1", 6397), timeout=0.3).close()
                self._alive_t = now
            except OSError:
                pass
        return now - self._alive_t < 20

    def close(self) -> None:
        self._mm.close()
        self._fast.close()

    def fast_sample(self) -> dict | None:
        """Lecture légère (~50 fois/s) de la dynamique de ta voiture."""
        d = self._fast.data
        if not d.generic.gameVersion or not d.telemetry.playerHasVehicle:
            return None
        tel = d.telemetry.telemInfo[d.telemetry.playerVehicleIdx]
        info = d.scoring.scoringInfo
        vs = d.scoring.vehScoringInfo
        if not vs[self._player_sc].mIsPlayer:
            n = min(info.mNumVehicles, len(vs))
            self._player_sc = next((i for i in range(n) if vs[i].mIsPlayer), 0)
        sc = vs[self._player_sc]
        return dynamics_sample(tel, sc, info)

    def spot_sample(self) -> dict | None:
        """Positions de toutes les voitures (lecture rapide) pour le spotter."""
        d = self._fast.data
        t = d.telemetry
        if not d.generic.gameVersion or not t.playerHasVehicle:
            return None
        me = t.telemInfo[t.playerVehicleIdx]
        others = []
        for i in range(min(t.activeVehicles, len(t.telemInfo))):
            if i == t.playerVehicleIdx:
                continue
            p = t.telemInfo[i].mPos
            others.append((p.x, p.z))
        return {"me": (me.mPos.x, me.mPos.z), "others": others, "t": me.mElapsedTime}

    def read(self) -> Snapshot:
        self._mm.update()
        d = self._mm.data
        s = Snapshot()
        if not d.generic.gameVersion or not self._game_alive(float(d.scoring.scoringInfo.mCurrentET)):
            return s
        s.connected = True

        tel_all = d.telemetry
        info = d.scoring.scoringInfo
        if not tel_all.playerHasVehicle:
            return s

        tel = tel_all.telemInfo[tel_all.playerVehicleIdx]
        n = min(info.mNumVehicles, len(d.scoring.vehScoringInfo))
        sc = None
        for i in range(n):
            v = d.scoring.vehScoringInfo[i]
            if v.mIsPlayer:
                sc = v
                break
        if sc is None:
            return s
        s.on_track = True

        s.track = _txt(info.mTrackName)
        s.car = _txt(sc.mVehicleName)
        s.car_class = _txt(sc.mVehicleClass)
        s.session = _session_name(info.mSession)
        s.game_phase = info.mGamePhase
        s.elapsed = info.mCurrentET
        if 0 < info.mMaxLaps < 10000:
            s.max_laps = info.mMaxLaps
        if info.mEndET > 0:
            s.time_left = max(0.0, info.mEndET - info.mCurrentET)

        s.laps_done = sc.mTotalLaps
        if info.mLapDist > 0:
            s.lap_frac = min(1.0, max(0.0, sc.mLapDist / info.mLapDist))
        s.last_lap = sc.mLastLapTime if sc.mLastLapTime > 0 else None
        s.best_lap = sc.mBestLapTime if sc.mBestLapTime > 0 else None
        s.position = sc.mPlace
        s.num_cars = n

        # position dans la catégorie
        cls = sc.mVehicleClass
        s.class_position = 1 + sum(
            1 for i in range(n)
            if d.scoring.vehScoringInfo[i].mVehicleClass == cls and d.scoring.vehScoringInfo[i].mPlace < sc.mPlace
        )

        s.lap_invalid = bool(tel.mLapInvalidated)
        s.sectors = split_sectors(sc.mLastSector1, sc.mLastSector2, sc.mLastLapTime)
        same = sorted((d.scoring.vehScoringInfo[i] for i in range(n)
                       if d.scoring.vehScoringInfo[i].mVehicleClass == cls), key=lambda v: v.mPlace)
        me = next((k for k, v in enumerate(same) if v.mIsPlayer), None)

        def gap(a, b):
            """Écart en secondes entre deux voitures (b derrière a), via l'écart au leader."""
            lap = sc.mLastLapTime if sc.mLastLapTime > 0 else (sc.mBestLapTime if sc.mBestLapTime > 0 else 0)
            g = (b.mTimeBehindLeader - a.mTimeBehindLeader) + (b.mLapsBehindLeader - a.mLapsBehindLeader) * lap
            return g if g > 0 else None

        def other(v):
            return {"name": _txt(v.mDriverName), "car": _txt(v.mVehicleName), "laps": v.mTotalLaps, "place": v.mPlace,
                    "last_lap": v.mLastLapTime if v.mLastLapTime > 0 else None,
                    "sectors": split_sectors(v.mLastSector1, v.mLastSector2, v.mLastLapTime),
                    "in_pits": bool(v.mInPits)}

        # toute ta catégorie, pour les questions sur une position précise (« où est P6 ? »)
        if me is not None:
            for k, v in enumerate(same):
                if v.mIsPlayer:
                    continue
                o = other(v)
                o["cpos"] = k + 1
                g = gap(v, sc) if k < me else gap(sc, v)
                o["gap"] = (g if k < me else -g) if g is not None else None   # > 0 : devant toi
                o["best"] = v.mBestLapTime if v.mBestLapTime > 0 else None
                s.rivals.append(o)
        if me is not None:
            s.ahead = other(same[me - 1]) if me > 0 else None
            s.behind = other(same[me + 1]) if me + 1 < len(same) else None
            if s.ahead:
                s.gap_class_ahead = gap(same[me - 1], sc)
            if s.behind:
                s.gap_class_behind = gap(sc, same[me + 1])

        # toutes les voitures pour la carte
        ahead_id = same[me - 1].mID if me is not None and me > 0 else None
        behind_id = same[me + 1].mID if me is not None and me + 1 < len(same) else None
        classes = []
        for i in range(n):
            v = d.scoring.vehScoringInfo[i]
            c = _txt(v.mVehicleClass)
            if c not in classes:
                classes.append(c)
            spd = math.sqrt(v.mLocalVel.x ** 2 + v.mLocalVel.y ** 2 + v.mLocalVel.z ** 2)
            edge = abs(v.mTrackEdge)
            s.cars.append({
                "x": v.mPos.x, "z": v.mPos.z, "id": v.mID, "spd": spd,
                "off": edge > 2 and abs(v.mPathLateral) > edge + 1.5,
                "f": (v.mLapDist / info.mLapDist) if info.mLapDist > 0 else 0.0,
                "s": sector_index(v.mSector), "c": classes.index(c), "cls": c, "p": v.mPlace,
                "me": bool(v.mIsPlayer), "pits": bool(v.mInPits),
                "rel": "ahead" if v.mID == ahead_id else "behind" if v.mID == behind_id else "",
                "best": v.mBestLapTime if v.mBestLapTime > 0 else None, "name": _txt(v.mDriverName),
            })
        s.session_code = info.mSession
        s.track_len = info.mLapDist
        s.tl_steps = tel.mTrackLimitsSteps
        s.tl_per_penalty = info.mTrackLimitsStepsPerPenalty
        s.dents = list(tel.mDentSeverity)
        s.flat = [bool(w.mFlat) for w in tel.mWheels]
        s.wheel_off = [bool(w.mDetached) for w in tel.mWheels]
        s.part_off = bool(tel.mDetached)
        s.driver = _txt(sc.mDriverName)
        s.penalties = max(0, int(sc.mNumPenalties))
        s.finish_status = int(sc.mFinishStatus)
        lt = tel.mElapsedTime - tel.mLapStartET
        s.lap_time = lt if 0 <= lt < 3600 else None

        s.gap_ahead = tel.mTimeGapCarAhead if tel.mTimeGapCarAhead > 0 else None
        s.gap_behind = tel.mTimeGapCarBehind if tel.mTimeGapCarBehind > 0 else None

        s.fuel = tel.mFuel
        s.fuel_capacity = tel.mFuelCapacity
        s.energy = tel.mVirtualEnergy if tel.mVirtualEnergy > 0 else None

        w = tel.mWheels
        s.tyre_wear = [w[i].mWear for i in range(4)]
        # température annoncée : couche de gomme intérieure (stable, c'est elle qui donne le grip et
        # c'est ce qu'affichent le jeu et les outils). La surface refroidit très vite dans les lignes droites
        # (un joueur avait 60 °C annoncés pour 85 °C en jeu) ; on la garde seulement en secours.
        surf = [sum(w[i].mTemperature) / 3 - 273.15 for i in range(4)]
        inner = [sum(w[i].mTireInnerLayerTemperature) / 3 - 273.15 for i in range(4)]
        s.tyre_temp = [n if -30 < n < 250 else t for n, t in zip(inner, surf)]
        s.tyre_surface_temp = surf
        s.tyre_pressure = [w[i].mPressure for i in range(4)]
        s.tyre_opt = float(w[0].mOptimalTemp)
        s.brake_temp = [float(w[i].mBrakeTemp) for i in range(4)]
        s.compound = _txt(tel.mFrontTireCompoundName)
        name = s.compound.lower()
        s.wet_tyres = any(k in name for k in ("wet", "rain", "pluie", "inter"))

        s.in_pits = bool(sc.mInPits)
        s.pit_state = sc.mPitState
        s.pit_stops = sc.mNumPitstops

        s.raining = info.mRaining
        s.wetness = info.mAvgPathWetness
        s.air_temp = info.mAmbientTemp
        s.track_temp = info.mTrackTemp
        y = info.mYellowFlagState
        if isinstance(y, bytes):
            y = y[0] if y else 0
        if y > 127:
            y -= 256
        s.yellow = 1 <= y <= 6 or s.game_phase == 6
        return s


def demo_track(f: float) -> tuple[float, float]:
    """Circuit imaginaire pour la démo (coordonnées en mètres)."""
    a = 2 * math.pi * f
    x = 900 * math.sin(a) + 160 * math.sin(2 * a)
    z = 480 * math.cos(a) + 110 * math.cos(3 * a) + 60 * math.sin(2 * a)
    return x, z


class DemoSource:
    """Course simulée (accélérée x10) pour tester l'appli sans lancer le jeu.

    Hypercar, 45 minutes, réservoir 90 L, énergie virtuelle ~22 tours,
    la pluie arrive vers la mi-course. La voiture rentre au stand quand
    l'ingénieur annonce "box".
    """

    SPEED = 10.0       # 1 seconde réelle = 10 secondes de course
    LAP = 98.0         # temps au tour de base (s)

    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.race_len = 45 * 60
        self.fuel = 90.0
        self.energy = 1.0
        self.wear = [1.0, 1.0, 1.0, 1.0]
        self.wet_tyres = False
        self.laps = 0
        self.lap_start = 0.0
        self.lap_time = self._lap_time()
        self.last_lap = None
        self.best_lap = None
        self.pit_until = None
        self.pit_requested = False
        self.stops = 0
        self.pos = 4
        self.gap_ahead = 3.4
        self.last_et = 0.0
        self.pending_fuel = 0.0
        self.pending_energy = 1.0
        self.pending_tyres = True
        self.my_sec = None
        self.rivals = {"ahead": ["M. Rossi", [31.9, 38.6, 27.4], None], "behind": ["J. Dupont", [32.4, 38.1, 27.9], None]}
        self.invalid = False
        # autres voitures : (catégorie, avance en tour, vitesse relative)
        self.others = [("Hypercar", 0.04 * k + random.uniform(0, 0.02), random.uniform(0.98, 1.02)) for k in range(1, 9)]
        self.others += [("LMGT3", 0.07 * k + 0.3, random.uniform(0.86, 0.9)) for k in range(1, 8)]

    def _lap_time(self) -> float:
        return self.LAP + random.uniform(-0.6, 0.9)

    def _rain(self, et: float) -> float:
        # pluie entre 40 % et 75 % de la course
        a, b = 0.40 * self.race_len, 0.75 * self.race_len
        if et < a or et > b:
            return 0.0
        return 0.7 * math.sin(math.pi * (et - a) / (b - a))

    # appelé par l'ingénieur quand il décide l'arrêt (pour la démo seulement)
    def request_pit(self, fuel_to_add: float, energy_target: float | None, tyres: bool) -> None:
        self.pit_requested = True
        self.pending_fuel = fuel_to_add
        self.pending_energy = energy_target if energy_target is not None else 1.0
        self.pending_tyres = tyres

    def close(self) -> None:
        pass

    # zones à problème simulées pour la démo
    DEMO_ISSUES = [((0.14, 0.17), "lock"), ((0.18, 0.215), "under_entry"), ((0.785, 0.82), "over_exit")]

    def spot_sample(self) -> dict | None:
        """Démo : une voiture vient se mettre à côté de toi de temps en temps (gauche puis droite)."""
        et = (time.monotonic() - self.t0) * self.SPEED
        f = ((et - self.lap_start) / self.lap_time) % 1
        x, z = demo_track(f)
        x2, z2 = demo_track(f + 0.001)
        n = math.hypot(x2 - x, z2 - z) or 1
        fx, fz = (x2 - x) / n, (z2 - z) / n
        lx, lz = -fz, fx                     # vecteur "gauche"
        others = []
        cyc = et % 60
        if 10 < cyc < 25:                    # voiture à gauche qui remonte puis repart
            along = (cyc - 17.5) * 1.2
            others.append((x + lx * 2.8 + fx * along, z + lz * 2.8 + fz * along))
        if 35 < cyc < 45:                    # voiture à droite
            along = (cyc - 40) * 1.5
            others.append((x - lx * 2.8 + fx * along, z - lz * 2.8 + fz * along))
        return {"me": (x, z), "others": others, "t": et}

    def fast_sample(self) -> dict | None:
        et = (time.monotonic() - self.t0) * self.SPEED
        if self.pit_until is not None:
            return {"lap": self.laps, "f": 0.0, "pits": True, "speed": 15, "lat": 0, "steer": 0, "thr": 0.2,
                    "brk": 0, "alpha": [0.0] * 4, "ratio": [0.0] * 4, "temps": [[80] * 3] * 4, "opt": 85,
                    "ride": [0.03, 0.05], "tc": 3, "abs": 2, "bias": 0.44, "farb": 4, "rarb": 3}
        f = min(0.999, (et - self.lap_start) / self.lap_time)
        # courbure du tracé de démo -> virages
        x0, z0 = demo_track(f - 0.003)
        x1, z1 = demo_track(f)
        x2, z2 = demo_track(f + 0.003)
        h1, h2 = math.atan2(z1 - z0, x1 - x0), math.atan2(z2 - z1, x2 - x1)
        dh = (h2 - h1 + math.pi) % (2 * math.pi) - math.pi
        ds = math.hypot(x2 - x1, z2 - z1) or 1
        curv = abs(dh) / ds
        cornering = curv > 1 / 300
        speed = 45 if cornering else 75
        lat = min(25, speed * speed * curv) if cornering else 0.5
        thr, brk = (0.15, 0.0) if cornering else (1.0, 0.0)
        a = [0.07 + random.uniform(-0.01, 0.01) for _ in range(4)] if cornering else [0.01] * 4
        ratio = [random.uniform(-0.03, 0.03) for _ in range(4)]
        for (lo, hi), kind in self.DEMO_ISSUES:
            if lo <= f <= hi:
                if kind == "lock":
                    brk, thr = 0.9, 0.0
                    ratio[0] = -0.35
                elif kind == "under_entry":
                    brk, thr, lat = 0.4, 0.0, 14
                    a[0] = a[1] = 0.13
                elif kind == "over_exit":
                    thr, brk, lat = 0.8, 0.0, 13
                    a[2] = a[3] = 0.13
                    ratio[2] = ratio[3] = 0.2
        hot = [[84, 90, 97], [97, 90, 84], [88, 89, 88], [88, 89, 88]]  # avant : trop de carrossage
        return {"lap": self.laps, "f": f, "pits": False, "speed": speed, "lat": lat, "steer": 0.2 if cornering else 0,
                "thr": thr, "brk": brk, "alpha": a, "ratio": ratio, "temps": hot, "opt": 85,
                "ride": [0.03, 0.05], "tc": 3, "abs": 2, "bias": 0.44, "farb": 4, "rarb": 3}

    def read(self) -> Snapshot:
        et = (time.monotonic() - self.t0) * self.SPEED
        dt = et - self.last_et
        self.last_et = et
        rain = self._rain(et)

        if self.pit_until is not None:
            if et >= self.pit_until:
                self.pit_until = None
        else:
            frac_dt = dt / self.lap_time
            wet_penalty = 1.0 + (0.6 * rain if not self.wet_tyres else 0.15 * (0.4 - rain))
            self.fuel -= 3.6 * frac_dt
            self.energy -= 0.045 * frac_dt
            for i in range(4):
                self.wear[i] -= (0.022 if i < 2 else 0.018) * frac_dt * wet_penalty
            self.gap_ahead = max(0.3, self.gap_ahead + random.uniform(-0.05, 0.04))

        lap_frac = (et - self.lap_start) / self.lap_time
        if lap_frac >= 1.0 and self.pit_until is None:
            self.laps += 1
            self.last_lap = self.lap_time
            base = [0.326, 0.392, 0.282]
            jit = [random.uniform(-0.25, 0.25) for _ in range(3)]
            raw = [self.lap_time * b + j for b, j in zip(base, jit)]
            k = self.lap_time / sum(raw)
            self.my_sec = [r * k for r in raw]
            for r in self.rivals.values():
                r[2] = [x + random.uniform(-0.3, 0.3) for x in r[1]]
            self.invalid = random.random() < 0.1
            self.best_lap = min(self.best_lap or 999, self.lap_time)
            self.lap_start = et
            self.lap_time = self._lap_time() * (1 + 0.08 * rain * (0 if self.wet_tyres else 1))
            lap_frac = 0.0
            if self.pit_requested:
                self.pit_requested = False
                self.stops += 1
                self.fuel = min(90.0, self.fuel + self.pending_fuel)
                self.energy = max(self.energy, self.pending_energy)
                if self.pending_tyres:
                    self.wear = [1.0] * 4
                    self.wet_tyres = rain > 0.25
                self.pit_until = et + 34
                self.pos = min(12, self.pos + 2)
            elif random.random() < 0.15 and self.pos > 1:
                self.pos -= 1

        s = Snapshot(connected=True, on_track=True)
        s.track, s.car, s.car_class = "Circuit de démo", "Hypercar démo", "Hypercar"
        s.session = "course"
        s.game_phase = 5
        s.elapsed = et
        s.time_left = max(0.0, self.race_len - et)
        s.laps_done = self.laps
        s.lap_frac = min(1.0, lap_frac)
        s.last_lap, s.best_lap = self.last_lap, self.best_lap
        s.position = s.class_position = self.pos
        s.num_cars = 18
        s.gap_ahead, s.gap_behind = self.gap_ahead, 2.1
        s.fuel, s.fuel_capacity = max(0.0, self.fuel), 90.0
        s.energy = max(0.0, self.energy)
        s.tyre_wear = [max(0.0, w) for w in self.wear]
        s.tyre_temp = [86, 88, 82, 83] if not rain else [70, 71, 68, 68]
        warm = min(1.0, et / 90)        # démo : pneus et freins froids au départ, chauds au bout d'1 min 30
        s.tyre_temp = [40 + (t - 40) * warm for t in s.tyre_temp]
        s.tyre_opt = 88.0
        s.brake_temp = [120 + 380 * warm] * 2 + [100 + 300 * warm] * 2
        s.tyre_pressure = [168, 169, 165, 166]
        s.wet_tyres = self.wet_tyres
        s.compound = "Pluie" if self.wet_tyres else "Medium"
        s.in_pits = self.pit_until is not None
        s.pit_state = 3 if s.in_pits else (1 if self.pit_requested else 0)
        s.pit_stops = self.stops
        s.raining = rain
        s.wetness = min(1.0, rain * 1.2)
        s.air_temp, s.track_temp = 21.0 - 4 * rain, 31.0 - 10 * rain
        s.sectors = self.my_sec
        my_total = self.laps + (0.0 if self.pit_until is not None else min(1.0, lap_frac))
        mx, mz = demo_track(my_total % 1)
        s.cars = [{"x": mx, "z": mz, "f": my_total % 1, "s": min(2, int((my_total % 1) * 3)), "c": 0,
                   "cls": "Hypercar", "p": self.pos, "me": True, "pits": s.in_pits, "rel": "", "id": 1, "spd": 60, "off": False,
                   "best": self.best_lap, "name": "Toi"}]
        hyper = sorted([o for o in self.others if o[0] == "Hypercar"], key=lambda o: -o[1])
        for i, (cls, off, spd) in enumerate(self.others):
            tot = (et / self.LAP) * spd + off
            f = tot % 1
            x, z = demo_track(f)
            rel = "ahead" if (cls, off, spd) == hyper[0] else "behind" if (cls, off, spd) == hyper[-1] else ""
            # démo : de temps en temps une voiture part à la faute pendant ~3 s de course
            off = int(et / 45) % len(self.others) == i and (et % 45) < 12
            s.cars.append({"x": x, "z": z, "f": f, "s": min(2, int(f * 3)), "c": 0 if cls == "Hypercar" else 1,
                           "cls": cls, "p": i + 1, "me": False, "pits": False, "rel": rel,
                           "id": 100 + i, "spd": 8 if off else 60, "off": off,
                           "best": self.LAP if cls == "Hypercar" else self.LAP * 1.1, "name": f"Pilote {i + 1}"})
        # démo : données pour les alertes
        s.session_code, s.track_len, s.driver = 10, 5200.0, "Toi"
        s.tl_per_penalty = 4
        s.tl_steps = min(4, int(et // 400))
        s.dents = [1, 0, 0, 0, 0, 0, 0, 1] if et > 700 else [0] * 8
        s.gap_class_ahead = self.gap_ahead
        s.gap_class_behind = max(0.4, 2.1 - et / 900)
        s.lap_invalid = self.invalid and lap_frac > 0.5
        s.lap_time = None if s.in_pits else et - self.lap_start
        s.penalties = 1 if 900 < et < 1150 else 0     # démo : une pénalité à purger
        if 1300 < et < 1400:                          # démo : la voiture devant rentre au stand
            self.rivals["ahead"][2] = None
        for key in ("ahead", "behind"):
            name, _, sec = self.rivals[key]
            setattr(s, key, {"name": name, "car": "Hypercar démo", "laps": self.laps,
                             "in_pits": key == "ahead" and 1300 < et < 1400,
                             "place": max(1, self.pos - 1) if key == "ahead" else self.pos + 1,
                             "last_lap": sum(sec) if sec else None, "sectors": sec})
        if s.time_left <= 0:
            s.game_phase = 8
            s.finish_status = 1
        return s
