"""
Lecture des données d'Assetto Corsa EVO (mémoire partagée officielle "acevo_pmf_*", Kunos v0.6+).

ACEvoSource renvoie le même Snapshot que LMUSource : le reste d'Apex Radio (stratégie essence,
alertes, radio, carte, spotter) fonctionne sans savoir de quel jeu viennent les données.

Ce que AC EVO ne donne pas (et qu'on calcule ou qu'on laisse vide) :
- les écarts devant / derrière : calculés à partir de la position des voitures sur la piste ;
- le nom, les tours et les chronos des autres pilotes : inconnus ;
- l'usure des pneus : toujours à 0 dans le jeu, on considère les pneus neufs ;
- le menu des stands : ne se pilote pas (PitCrew est désactivé hors LMU).
"""

from __future__ import annotations

import ctypes as C
import math
import sys
import time

# ---------------------------------------------------------------- structures (doc Kunos, pack 4)
# D'après la documentation officielle Kunos (ACE_SharedFileOut, v. 0.6) :
# en-tête C avec "#pragma pack(4)".

PACK = 4


def S(name, fields, pack=PACK):
    return type(name, (C.Structure,), {"_pack_": pack, "_fields_": fields})


f32, i32, u32, i16, u16, i8, u8, u64, b = (C.c_float, C.c_int32, C.c_uint32, C.c_int16,
                                          C.c_uint16, C.c_int8, C.c_uint8, C.c_uint64, C.c_bool)


def A(t, n):
    return t * n


Physics = S("Physics", [
    ("packetId", i32), ("gas", f32), ("brake", f32), ("fuel", f32), ("gear", i32), ("rpms", i32),
    ("steerAngle", f32), ("speedKmh", f32), ("velocity", A(f32, 3)), ("accG", A(f32, 3)),
    ("wheelSlip", A(f32, 4)), ("wheelLoad", A(f32, 4)), ("wheelsPressure", A(f32, 4)),
    ("wheelAngularSpeed", A(f32, 4)), ("tyreWear", A(f32, 4)), ("tyreDirtyLevel", A(f32, 4)),
    ("tyreCoreTemperature", A(f32, 4)), ("camberRAD", A(f32, 4)), ("suspensionTravel", A(f32, 4)),
    ("drs", f32), ("tc", f32), ("heading", f32), ("pitch", f32), ("roll", f32), ("cgHeight", f32),
    ("carDamage", A(f32, 5)), ("numberOfTyresOut", i32), ("pitLimiterOn", i32), ("abs", f32),
    ("kersCharge", f32), ("kersInput", f32), ("autoShifterOn", i32), ("rideHeight", A(f32, 2)),
    ("turboBoost", f32), ("ballast", f32), ("airDensity", f32), ("airTemp", f32), ("roadTemp", f32),
    ("localAngularVel", A(f32, 3)), ("finalFF", f32), ("performanceMeter", f32),
    ("engineBrake", i32), ("ersRecoveryLevel", i32), ("ersPowerLevel", i32), ("ersHeatCharging", i32),
    ("ersIsCharging", i32), ("kersCurrentKJ", f32), ("drsAvailable", i32), ("drsEnabled", i32),
    ("brakeTemp", A(f32, 4)), ("clutch", f32), ("tyreTempI", A(f32, 4)), ("tyreTempM", A(f32, 4)),
    ("tyreTempO", A(f32, 4)), ("isAIControlled", i32), ("tyreContactPoint", A(A(f32, 3), 4)),
    ("tyreContactNormal", A(A(f32, 3), 4)), ("tyreContactHeading", A(A(f32, 3), 4)),
    ("brakeBias", f32), ("localVelocity", A(f32, 3)), ("P2PActivations", i32), ("P2PStatus", i32),
    ("currentMaxRpm", i32), ("mz", A(f32, 4)), ("fx", A(f32, 4)), ("fy", A(f32, 4)),
    ("slipRatio", A(f32, 4)), ("slipAngle", A(f32, 4)), ("tcinAction", i32), ("absInAction", i32),
    ("suspensionDamage", A(f32, 4)), ("tyreTemp", A(f32, 4)), ("waterTemp", f32),
    ("brakeTorque", A(f32, 4)), ("frontBrakeCompound", i32), ("rearBrakeCompound", i32),
    ("padLife", A(f32, 4)), ("discLife", A(f32, 4)), ("ignitionOn", i32), ("starterEngineOn", i32),
    ("isEngineRunning", i32), ("kerbVibration", f32), ("slipVibrations", f32), ("roadVibrations", f32),
    ("absVibrations", f32),
])

Tyre = S("Tyre", [
    ("slip", f32), ("lock", b), ("pressure", f32), ("tempC", f32), ("brakeTempC", f32),
    ("brakePressure", f32), ("tempLeft", f32), ("tempCenter", f32), ("tempRight", f32),
    ("compoundFront", A(C.c_char, 33)), ("compoundRear", A(C.c_char, 33)), ("normPressure", f32),
    ("normTempLeft", f32), ("normTempCenter", f32), ("normTempRight", f32), ("normBrakeTemp", f32),
    ("normTempCore", f32), ("_pad", A(u8, 128)),
])
Damage = S("Damage", [
    ("front", f32), ("rear", f32), ("left", f32), ("right", f32), ("center", f32),
    ("suspLF", f32), ("suspRF", f32), ("suspLR", f32), ("suspRR", f32), ("_pad", A(u8, 92)),
])
PitInfo = S("PitInfo", [
    ("damage", i8), ("fuel", i8), ("tyresLF", i8), ("tyresRF", i8), ("tyresLR", i8), ("tyresRR", i8),
    ("_pad", A(u8, 58)),
])
Electronics = S("Electronics", [
    ("tcLevel", i8), ("tcCutLevel", i8), ("absLevel", i8), ("escLevel", i8), ("ebbLevel", i8),
    ("brakeBias", f32), ("engineMapLevel", i8), ("turboLevel", f32), ("ersDeploymentMap", i8),
    ("ersRechargeMap", f32), ("ersHeatCharging", b), ("ersOvertake", b), ("drsOpen", b),
    ("diffPower", i8), ("diffCoast", i8), ("frontBump", i8), ("frontRebound", i8), ("rearBump", i8),
    ("rearRebound", i8), ("ignitionOn", b), ("pitLimiterOn", b), ("performanceMode", i8),
    ("_pad", A(u8, 88)),
])
Instr = S("Instr", [
    ("mainLight", i8), ("specialLight", i8), ("cockpitLight", i8), ("wiper", i8), ("rainLights", b),
    ("dirLeft", b), ("dirRight", b), ("flashing", b), ("warning", b), ("display", i8),
    ("displayPage", A(i8, 16)), ("headlights", b), ("_pad", A(u8, 101)),
])
Session = S("Session", [
    ("phaseName", A(C.c_char, 33)), ("timeLeft", A(C.c_char, 15)), ("timeLeftMs", i32),
    ("waitTime", A(C.c_char, 15)), ("totalLap", i32), ("currentLap", i32), ("lightsOn", i32),
    ("lightsMode", i32), ("lapLengthKm", f32), ("endSessionFlag", i32),
    ("timeToNextSession", A(C.c_char, 15)), ("disconnected", b), ("restartSeason", b),
    ("uiEnableDrive", b), ("uiEnableSetup", b), ("readyBlinking", b), ("waitingPlayers", b),
    ("_pad", A(u8, 143)),
])
Timing = S("Timing", [
    ("currentLaptime", A(C.c_char, 15)), ("deltaCurrent", A(C.c_char, 15)), ("deltaCurrentP", i32),
    ("lastLaptime", A(C.c_char, 15)), ("deltaLast", A(C.c_char, 15)), ("deltaLastP", i32),
    ("bestLaptime", A(C.c_char, 15)), ("idealLaptime", A(C.c_char, 15)), ("totalTime", A(C.c_char, 15)),
    ("isInvalid", b), ("_pad", A(u8, 138)),
])
Assists = S("Assists", [
    ("autoGear", u8), ("autoBlip", u8), ("autoClutch", u8), ("autoClutchStart", u8),
    ("manualIgnition", u8), ("autoPitLimiter", u8), ("standingStart", u8), ("autoSteer", f32),
    ("arcadeStability", f32), ("_pad", A(u8, 48)),
])


def graphics_fields():
    return [
        ("packetId", i32), ("status", i32), ("focusedCarIdA", u64), ("focusedCarIdB", u64),
        ("playerCarIdA", u64), ("playerCarIdB", u64), ("rpm", u16), ("rpmLimiter", b),
        ("changeUp", b), ("changeDown", b), ("tcActive", b), ("absActive", b), ("escActive", b),
        ("launchActive", b), ("ignitionOn", b), ("engineRunning", b), ("kersCharging", b),
        ("wrongWay", b), ("drsAvailable", b), ("batteryCharging", b), ("maxKjLap", b),
        ("maxChargeKjLap", b), ("speedKmh", i16), ("speedMph", i16), ("speedMs", i16),
        ("pitSpeedingDelta", f32), ("gear", i16), ("rpmPercent", f32), ("gasPercent", f32),
        ("brakePercent", f32), ("handbrakePercent", f32), ("clutchPercent", f32),
        ("steeringPercent", f32), ("ffbStrength", f32), ("carFfbMult", f32), ("waterTempPercent", f32),
        ("waterPressure", f32), ("fuelPressure", f32), ("waterTempC", i8), ("airTempC", i8),
        ("oilTempC", f32), ("oilPressure", f32), ("exhaustTempC", f32), ("gX", f32), ("gY", f32),
        ("gZ", f32), ("turboBoost", f32), ("turboBoostLevel", f32), ("turboBoostPerc", f32),
        ("steerDegrees", i32), ("currentKm", f32), ("totalKm", u32), ("totalDrivingTime", u32),
        ("todH", i32), ("todM", i32), ("todS", i32), ("deltaTimeMs", i32), ("currentLapTimeMs", i32),
        ("predictedLapTimeMs", i32), ("fuelL", f32), ("fuelPercent", f32), ("fuelLPerKm", f32),
        ("kmPerFuelL", f32), ("torque", f32), ("bhp", i32), ("tyreLF", Tyre), ("tyreRF", Tyre),
        ("tyreLR", Tyre), ("tyreRR", Tyre), ("npos", f32), ("kersChargePerc", f32),
        ("kersCurrentPerc", f32), ("controlLockTime", f32), ("damage", Damage), ("carLocation", i32),
        ("pitInfo", PitInfo), ("fuelUsed", f32), ("fuelPerLapA", f32), ("lapsPossible", f32),
        ("batteryTemp", f32), ("batteryVoltage", f32), ("instFuelLPerKm", f32), ("instKmPerL", f32),
        ("gearRpmWindow", f32), ("instr", Instr), ("instrMin", Instr), ("instrMax", Instr),
        ("elec", Electronics), ("elecMin", Electronics), ("elecMax", Electronics),
        ("elecModifiable", Electronics), ("totalLapCount", i32), ("position", u32),
        ("totalDrivers", u32), ("lastLapMs", i32), ("bestLapMs", i32), ("flag", i32),
        ("globalFlag", i32), ("maxGears", u32), ("engineType", i32), ("hasKers", b),
        ("isLastLap", b), ("perfModeName", A(C.c_char, 33)), ("diffCoastRaw", f32),
        ("diffPowerRaw", f32), ("raceCutGainedMs", i32), ("distanceToDeadline", i32),
        ("raceCutDelta", f32), ("session", Session), ("timing", Timing), ("ping", i32),
        ("latency", i32), ("cpu", i32), ("cpuAvg", i32), ("qos", i32), ("qosAvg", i32), ("fps", i32),
        ("fpsAvg", i32), ("driverName", A(C.c_char, 33)), ("driverSurname", A(C.c_char, 33)),
        ("carModel", A(C.c_char, 33)), ("inPitBox", b), ("inPitLane", b), ("validLap", b),
        ("carCoords", A(A(f32, 3), 60)), ("gapAhead", f32), ("gapBehind", f32), ("activeCars", u8),
        ("fuelPerLap", f32), ("fuelEstimatedLaps", f32), ("assists", Assists), ("maxFuel", f32),
        ("maxTurboBoost", f32), ("singleCompound", b), ("carIds", A(A(u64, 2), 60)),
    ]


Graphics = S("Graphics", graphics_fields())

Static = S("Static", [
    ("smVersion", A(C.c_char, 15)), ("acEvoVersion", A(C.c_char, 15)), ("session", i32),
    ("sessionName", A(C.c_char, 33)), ("eventId", u8), ("sessionId", u8), ("startingGrip", i32),
    ("ambientC", f32), ("groundC", f32), ("staticWeather", b), ("timedRace", b), ("online", b),
    ("numberOfSessions", i32), ("nation", A(C.c_char, 33)), ("longitude", f32), ("latitude", f32),
    ("track", A(C.c_char, 33)), ("trackConfig", A(C.c_char, 33)), ("trackLengthM", f32),
])




# ---------------------------------------------------------------- lecture

def _txt(v) -> str:
    if isinstance(v, bytes):
        return v.split(b"\0", 1)[0].decode("utf-8", "replace").strip()
    return str(v)


PSI_TO_KPA = 6.894757


class _Page:
    """Une zone de mémoire partagée Windows, ouverte en lecture seule."""

    def __init__(self, name: str) -> None:
        self.name = "Local\\" + name
        self.ptr = None

    def open(self) -> bool:
        if self.ptr:
            return True
        import ctypes.wintypes as W
        k32 = C.WinDLL("kernel32", use_last_error=True)
        k32.OpenFileMappingW.restype = W.HANDLE
        k32.OpenFileMappingW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
        k32.MapViewOfFile.restype = C.c_void_p
        k32.MapViewOfFile.argtypes = [W.HANDLE, W.DWORD, W.DWORD, W.DWORD, C.c_size_t]
        h = k32.OpenFileMappingW(4, False, self.name)   # FILE_MAP_READ
        if not h:
            return False
        p = k32.MapViewOfFile(h, 4, 0, 0, 0)
        if not p:
            return False
        self.ptr = p
        return True

    def read(self, cls):
        return cls.from_buffer_copy(C.string_at(self.ptr, C.sizeof(cls)))


def _xz(c) -> tuple[float, float]:
    """Coordonnées AC EVO -> repère d'Apex Radio (celui de LMU). L'axe x d'AC EVO est inversé :
    sans ça, le spotter annonçait « à droite » pour une voiture à gauche."""
    return -c[0], c[2]


class TrackLine:
    """Tracé appris sur tes propres tours : position (x, z) -> progression dans le tour (0..1).
    Sert à placer les autres voitures, dont AC EVO ne donne que les coordonnées."""

    N = 400

    def __init__(self) -> None:
        self.pts: list = [None] * self.N
        self.track = ""

    def reset(self, track: str) -> None:
        self.pts = [None] * self.N
        self.track = track

    def learn(self, x: float, z: float, f: float) -> None:
        if 0 <= f < 1:
            self.pts[int(f * self.N) % self.N] = (x, z)

    def ready(self) -> bool:
        return sum(1 for p in self.pts if p) > self.N * 0.6

    def where(self, x: float, z: float) -> float | None:
        best, bf = None, None
        for i, p in enumerate(self.pts):
            if p:
                d = (p[0] - x) ** 2 + (p[1] - z) ** 2
                if best is None or d < best:
                    best, bf = d, (i + 0.5) / self.N
        if best is None or best > 60 ** 2:   # trop loin du tracé (voie des stands, garage…)
            return None
        return bf


def _session(name: str, code: int) -> tuple[str, int]:
    n = name.lower()
    if "race" in n or "course" in n or code == 1:
        return "course", 10
    if "qual" in n:
        return "qualif", 5
    if "warm" in n:
        return "warmup", 9
    return "essais", 0


def _phase(name: str) -> int:
    """Phase AC EVO -> code de phase LMU utilisé par Apex Radio (5 = vert, 8 = terminée)."""
    n = name.lower()
    if not n:
        return 0
    if n.startswith("start") or "countdown" in n or "formation" in n:
        return 4
    if "ended" in n or "pitbox" in n or "finish" in n or "results" in n:
        return 8
    return 5


class ACEvoSource:
    """Lecture en direct d'Assetto Corsa EVO."""

    game = "acevo"

    def __init__(self) -> None:
        self.pages = {k: _Page("acevo_pmf_" + k) for k in ("physics", "graphics", "static")}
        self.line = TrackLine()
        self._pkt = None
        self._pkt_t = 0.0
        self._t0 = time.monotonic()
        self._sess_key = None
        self._prev = {}          # dernière position de chaque voiture (vitesse)
        self._stops = 0
        self._was_box = False
        self._last_spd = {}

    def _open(self) -> bool:
        return sys.platform == "win32" and all(p.open() for p in self.pages.values())

    def alive(self) -> bool:
        """Le jeu tourne et une séance est chargée (la mémoire reste après la fermeture : on vérifie que ça bouge)."""
        if not self._open():
            return False
        try:
            g = self.pages["graphics"].read(Graphics)
        except Exception:
            return False
        now = time.time()
        if g.packetId != self._pkt:
            self._pkt, self._pkt_t = g.packetId, now
        return g.status != 0 and now - self._pkt_t < 10

    def close(self) -> None:
        pass

    def _player_index(self, g) -> int | None:
        me = (g.playerCarIdA, g.playerCarIdB)
        for i in range(60):
            if (g.carIds[i][0], g.carIds[i][1]) == me and (me[0] or me[1]):
                return i
        return None

    def spot_sample(self) -> dict | None:
        if not self._open():
            return None
        g = self.pages["graphics"].read(Graphics)
        if g.status != 2:
            return None
        pi = self._player_index(g)
        if pi is None:
            return None
        n = max(1, int(g.activeCars))
        mx, mz = _xz(g.carCoords[pi])
        if not (g.inPitLane or g.carLocation in (1, 2, 3)):
            self.line.learn(mx, mz, float(g.npos))   # apprend le tracé ~25 fois/s
        others = [_xz(g.carCoords[i]) for i in range(min(n, 60)) if i != pi]
        return {"me": (mx, mz), "others": others, "t": time.monotonic() - self._t0}

    def fast_sample(self) -> dict | None:
        """Dynamique de ta voiture (~50 fois/s) pour l'analyse du pilotage : blocages, patinage, sous/survirage.
        Mêmes clés et mêmes unités que LMU (voir telemetry.dynamics_sample)."""
        if not self._open():
            return None
        g = self.pages["graphics"].read(Graphics)
        if g.status != 2:
            return None
        p = self.pages["physics"].read(Physics)
        core = [float(x) for x in p.tyreCoreTemperature]
        bias = float(p.brakeBias)                       # part à l'avant (0,62) ; LMU donne la part à l'arrière
        return {
            "lap": int(g.totalLapCount), "f": min(1.0, max(0.0, float(g.npos))),
            "pits": bool(g.inPitLane) or int(g.carLocation) in (1, 2, 3),
            "speed": max(0.0, float(p.speedKmh) / 3.6),
            "lat": float(p.accG[0]) * 9.81,              # AC EVO : en g ; LMU : en m/s²
            "steer": float(p.steerAngle), "thr": float(p.gas), "brk": float(p.brake),
            "alpha": [abs(float(x)) for x in p.slipAngle],   # radians, comme LMU
            "ratio": [float(x) for x in p.slipRatio],        # négatif = roue qui bloque, comme LMU
            # AC EVO ne donne pas la température intérieur/milieu/extérieur : on prend le cœur du pneu partout
            "temps": [[t, t, t] for t in core],
            "opt": 85.0,
            "ride": [float(p.rideHeight[0]) / 1000, float(p.rideHeight[1]) / 1000],   # mm -> m
            "tc": float(g.elec.tcLevel), "abs": float(g.elec.absLevel),
            "bias": (1 - bias) if 0.2 < bias < 0.8 else None,
            "farb": None, "rarb": None,
            "btemp": [float(x) for x in p.brakeTemp],
        }

    def read(self):
        from telemetry import Snapshot
        s = Snapshot()
        if not self.alive():
            return s
        g = self.pages["graphics"].read(Graphics)
        p = self.pages["physics"].read(Physics)
        st = self.pages["static"].read(Static)
        s.connected = True
        s.game = "acevo"
        if g.status not in (2, 3):
            return s
        s.on_track = True

        track = _txt(st.track)
        cfg = _txt(st.trackConfig)
        s.track = track + (f" {cfg}" if cfg and cfg.lower() not in ("gp", "default", track.lower()) else "")
        # nom propre à AC EVO : la carte, la conso et les records ne se mélangent pas avec le Monza de LMU
        s.track += " (AC EVO)"
        s.car = _txt(g.carModel)
        s.car_class = s.car or "AC EVO"
        sname = _txt(st.sessionName)
        s.session, s.session_code = _session(sname, st.session)
        phase_name = _txt(g.session.phaseName)
        s.game_phase = _phase(phase_name)

        key = (track, sname, st.sessionId, st.eventId)
        if key != self._sess_key:
            self._sess_key = key
            self._t0 = time.monotonic()
            self._stops = 0
            self._prev.clear()
            if self.line.track != track:
                self.line.reset(track)
        s.elapsed = time.monotonic() - self._t0

        ms = g.session.timeLeftMs
        if s.session == "course" and g.session.totalLap > 0:
            # course de 4 tours annoncée « 12 minutes, environ 6 tours » (20/11) : timedRace était vrai
            s.max_laps = int(g.session.totalLap)
        elif st.timedRace or s.session != "course":
            if "overtime" in phase_name.lower():
                s.time_left = 0.0
            elif ms > 0:
                s.time_left = ms / 1000
        elif g.session.totalLap > 0:
            s.max_laps = int(g.session.totalLap)

        s.laps_done = max(0, int(g.totalLapCount))
        s.lap_frac = min(1.0, max(0.0, float(g.npos)))
        s.last_lap = g.lastLapMs / 1000 if 0 < g.lastLapMs < 3_600_000 else None
        s.best_lap = g.bestLapMs / 1000 if 0 < g.bestLapMs < 3_600_000 else None
        lt = g.currentLapTimeMs / 1000
        s.lap_time = lt if 0 <= lt < 3600 else None
        s.num_cars = int(g.activeCars or g.totalDrivers)
        # AC EVO compte la place à partir de 0 (le leader est 0) : 4e annoncé « P3 » au test du 19/11
        s.position = min(int(g.position) + 1, max(1, s.num_cars))
        s.class_position = s.position
        s.lap_invalid = not bool(g.validLap)
        s.driver = (_txt(g.driverName) + " " + _txt(g.driverSurname)).strip()
        s.finish_status = 1 if s.game_phase == 8 or (g.flag == 8 and s.session == "course") else 0

        s.fuel = float(g.fuelL)
        s.fuel_capacity = float(g.maxFuel)
        s.energy = None
        s.limiter = bool(g.elec.pitLimiterOn)
        s.speed = max(0.0, float(p.speedKmh) / 3.6)

        # pneus et freins
        tyres = (g.tyreLF, g.tyreRF, g.tyreLR, g.tyreRR)
        s.tyre_wear = [1.0] * 4                       # AC EVO ne donne pas l'usure
        core = [float(x) for x in p.tyreCoreTemperature]
        surf = [(t.tempLeft + t.tempCenter + t.tempRight) / 3 for t in tyres]
        s.tyre_temp = core
        s.tyre_inner_temp = core
        s.tyre_carcass_temp = core
        s.tyre_surface_temp = surf
        s.tyre_pressure = [float(x) * PSI_TO_KPA for x in p.wheelsPressure]
        s.brake_temp = [float(x) for x in p.brakeTemp]
        s.compound = _txt(g.tyreLF.compoundFront) or _txt(g.tyreLF.compoundRear)
        low = s.compound.lower()
        s.wet_tyres = any(k in low for k in ("wet", "rain", "pluie", "inter"))
        s.tyre_opt = 0.0                              # inconnu : les alertes prennent leur valeur par défaut

        # stands
        loc = int(g.carLocation)
        s.in_pits = bool(g.inPitLane) or loc in (1, 2, 3)
        s.pit_state = 3 if g.inPitBox else 2 if loc == 2 else 4 if loc == 3 else 0
        if g.inPitBox and not self._was_box:
            self._stops += 1
        self._was_box = bool(g.inPitBox)
        s.pit_stops = self._stops

        # météo et drapeaux
        s.air_temp = float(p.airTemp)
        s.track_temp = float(p.roadTemp)
        s.yellow = g.flag == 5 or g.globalFlag == 5
        s.track_len = float(st.trackLengthM) or (g.session.lapLengthKm * 1000)

        # dégâts carrosserie : AC EVO donne 0..1 par zone, Apex attend 0/1/2 sur 8 zones
        def lvl(v):
            return 0 if v < 0.15 else 1 if v < 0.6 else 2
        d = g.damage
        s.dents = [lvl(d.front), lvl(d.right), lvl(d.rear), lvl(d.left), lvl(d.center), 0, 0, 0]

        try:
            s.car_state = {"lights": g.instr.mainLight > 0, "limiter": bool(g.elec.pitLimiterOn),
                           "wipers": int(g.instr.wiper), "tc": int(g.elec.tcLevel), "abs": int(g.elec.absLevel),
                           "map": int(g.elec.engineMapLevel), "rpm": int(p.rpms),
                           "bias": round(100 * g.elec.brakeBias, 1) if 0 < g.elec.brakeBias < 1 else None}
        except Exception:
            s.car_state = {}

        # voitures : coordonnées -> progression dans le tour grâce au tracé appris
        pi = self._player_index(g)
        n = min(60, max(1, int(g.activeCars)))
        now = time.monotonic()
        if pi is not None and not s.in_pits:
            self.line.learn(*_xz(g.carCoords[pi]), s.lap_frac)
        L = s.track_len or 0
        ref = s.best_lap or s.last_lap
        gaps_ahead, gaps_behind = [], []
        for i in range(n):
            x, y, z = g.carCoords[i]
            if not (x or y or z):
                continue
            x, z = _xz(g.carCoords[i])
            mine = i == pi
            f = s.lap_frac if mine else (self.line.where(x, z) if self.line.ready() else None)
            prev = self._prev.get(i)
            spd = math.hypot(x - prev[0], z - prev[1]) / max(1e-3, now - prev[2]) if prev else 0.0
            self._prev[i] = (x, z, now)
            if spd > 120:      # téléportation (retour au stand)
                spd = 0.0
            s.cars.append({"x": x, "z": z, "id": i, "spd": spd, "off": False, "f": f if f is not None else 0.0,
                           "s": 0, "c": 0, "cls": s.car_class, "p": s.position if mine else 0, "me": mine,
                           "pits": f is None and not mine, "rel": "", "best": s.best_lap if mine else None, "name": ""})
            if not mine and f is not None and L and ref and not s.in_pits:
                d = (f - s.lap_frac) % 1
                t = d * ref
                if d < 0.5:
                    gaps_ahead.append(t)
                else:
                    gaps_behind.append((1 - d) * ref)
        if self.line.ready():
            s.gap_ahead = min(gaps_ahead) if gaps_ahead else None
            s.gap_behind = min(gaps_behind) if gaps_behind else None
        return s
