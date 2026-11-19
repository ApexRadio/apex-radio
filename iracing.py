"""
Lecture des données d'iRacing (iRacing SDK officiel, mémoire partagée "Local\\IRSDKMemMapFileName").

IRacingSource renvoie le même Snapshot que LMUSource : la stratégie essence, les écarts, les annonces
de trafic, la radio et les références de tour fonctionnent sans savoir de quel jeu viennent les données.

Ce qu'iRacing ne donne pas (vérifié sur une vraie course, le 18/11/2026) :
- la température et l'usure des pneus en roulant : elles ne changent qu'au stand. On garde l'usure
  mesurée au dernier arrêt et on ne donne pas de température (pas de fausse alerte « pneus froids ») ;
- la température des freins, l'énergie virtuelle, les dégâts par zone ;
- la position (x, z) des voitures : on refait le tracé à partir de ta vitesse et de ton cap,
  puis on place les autres voitures dessus grâce à leur progression dans le tour ;
- l'angle de glisse de chaque pneu : on l'estime avec le volant et la rotation de la voiture
  (si elle tourne moins que le volant ne le demande = sous-virage, plus = survirage).
Le spotter utilise directement l'info « voiture à gauche / à droite » d'iRacing.
"""

from __future__ import annotations

import ctypes as C
import math
import re
import sys
import time

MAP_NAME = "Local\\IRSDKMemMapFileName"
TYPES = {0: (C.c_char, 1), 1: (C.c_bool, 1), 2: (C.c_int32, 4), 3: (C.c_uint32, 4), 4: (C.c_float, 4), 5: (C.c_double, 8)}

# drapeaux de séance (irsdk_Flags)
F_YELLOW, F_YELLOW_WAVING, F_CAUTION, F_CAUTION_WAVING = 0x0008, 0x0100, 0x4000, 0x8000
F_BLACK = 0x00010000
PIT_LIMITER = 0x10       # EngineWarnings : limiteur des stands
WHEELBASE = 2.7          # m : empattement supposé (iRacing ne le donne pas), sert à estimer le sous/survirage


class VarBuf(C.Structure):
    _fields_ = [("tickCount", C.c_int32), ("bufOffset", C.c_int32), ("pad", C.c_int32 * 2)]


class Header(C.Structure):
    _fields_ = [("ver", C.c_int32), ("status", C.c_int32), ("tickRate", C.c_int32),
                ("sessionInfoUpdate", C.c_int32), ("sessionInfoLen", C.c_int32), ("sessionInfoOffset", C.c_int32),
                ("numVars", C.c_int32), ("varHeaderOffset", C.c_int32), ("numBuf", C.c_int32), ("bufLen", C.c_int32),
                ("pad", C.c_int32 * 2), ("varBuf", VarBuf * 4)]


class VarHeader(C.Structure):
    _fields_ = [("type", C.c_int32), ("offset", C.c_int32), ("count", C.c_int32), ("countAsTime", C.c_bool),
                ("pad", C.c_char * 3), ("name", C.c_char * 32), ("desc", C.c_char * 64), ("unit", C.c_char * 32)]


# ---------------------------------------------------------------- infos de séance (texte YAML d'iRacing)
def parse_session(text: str) -> dict:
    """Lecture simple du YAML d'iRacing : les clés de premier niveau de chaque section, et les listes
    de premier niveau (Sessions, Drivers, DriverTires). Pas besoin de bibliothèque YAML."""
    out: dict = {}
    sec = None
    item = None
    last_list = "items"
    for line in text.splitlines():
        m = re.match(r"^(\w+):\s*$", line)
        if m:
            sec, item = m.group(1), None
            out.setdefault(sec, {})
            continue
        if sec is None:
            continue
        m = re.match(r"^ (\w+):\s*(.*)$", line)
        if m:
            out[sec][m.group(1)] = m.group(2).strip().strip('"')
            item = None
            last_list = m.group(1)
            continue
        m = re.match(r"^  (\w+):\s*(.*)$", line)          # sous-bloc (WeekendOptions…) : mis à plat
        if m and item is None:
            out[sec].setdefault(m.group(1), m.group(2).strip().strip('"'))
            continue
        m = re.match(r"^ - (\w+):\s*(.*)$", line)
        if m:
            item = {m.group(1): m.group(2).strip().strip('"')}
            out[sec].setdefault("_" + last_list, []).append(item)
            continue
        m = re.match(r"^   (\w+):\s*(.*)$", line)
        if m and item is not None:
            item[m.group(1)] = m.group(2).strip().strip('"')
    return out


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).split()[0])
    except Exception:
        return default


def _session(kind: str) -> tuple[str, int]:
    k = kind.lower()
    if "race" in k:
        return "course", 10
    if "qual" in k:
        return "qualif", 5
    if "warm" in k:
        return "warmup", 9
    return "essais", 0


class TrackLine:
    """Ton tracé, refait à partir de ta vitesse et de ton cap (iRacing ne donne pas les coordonnées).
    Appris sur un tour complet hors stands, puis refermé (petit écart réparti sur le tour)."""

    N = 400

    def __init__(self) -> None:
        self.reset("")

    def reset(self, track: str) -> None:
        self.track = track
        self.pts: list = [None] * self.N
        self.ready = False
        self.cur: list = []
        self.x = self.z = 0.0
        self.last_f = None
        self.t = None

    def step(self, f: float, vx: float, vy: float, yaw: float, t: float, pits: bool) -> None:
        if self.ready:
            return
        if self.t is None or pits or t <= self.t or t - self.t > 0.5:
            self.t, self.cur, self.last_f = t, [], None
            return
        dt, self.t = t - self.t, t
        self.x += (vx * math.cos(yaw) - vy * math.sin(yaw)) * dt
        self.z += (vx * math.sin(yaw) + vy * math.cos(yaw)) * dt
        if self.last_f is not None and f < 0.05 and self.last_f > 0.95:   # ligne passée
            if self.cur and self.cur[0][0] < 0.02 and len(self.cur) > 300:
                self._close(self.cur + [(1.0, self.x, self.z)])
                return
            self.cur = []
        if self.last_f is None or f >= self.last_f or (f < 0.05 and self.last_f > 0.95):
            self.cur.append((f, self.x, self.z))
        self.last_f = f

    def _close(self, pts) -> None:
        x0, z0 = pts[0][1], pts[0][2]
        ex, ez = pts[-1][1] - x0, pts[-1][2] - z0          # écart de fermeture
        bins = [None] * self.N
        for f, x, z in pts[:-1]:
            k = min(self.N - 1, int(f * self.N))
            bins[k] = (x - x0 - ex * f, -(z - z0 - ez * f))
        known = [i for i in range(self.N) if bins[i]]
        if len(known) < self.N * 0.8:
            return
        for i in range(self.N):
            if not bins[i]:
                a = max((j for j in known if j < i), default=known[-1])
                b = min((j for j in known if j > i), default=known[0])
                bins[i] = ((bins[a][0] + bins[b][0]) / 2, (bins[a][1] + bins[b][1]) / 2)
        self.pts, self.ready = bins, True
        print(f"  iRacing : tracé appris ({self.track}, écart de fermeture {math.hypot(ex, ez):.0f} m)")

    def at(self, f: float):
        if not self.ready:
            return None
        return self.pts[int((f % 1) * self.N) % self.N]


class IRacingSource:
    """Lecture en direct d'iRacing."""

    game = "iracing"

    def __init__(self) -> None:
        self.ptr = None
        self.vars: dict = {}
        self.nvars = 0
        self.info_v = None
        self.info: dict = {}
        self.line = TrackLine()
        self._last_tick = None
        self._tick_t = 0.0
        self._stops = 0
        self._was_stall = False
        self._wear = [1.0] * 4
        self._prev_f: dict = {}
        self._k = []                 # rapport volant / rotation appris en virage léger
        self._sess = None
        self._done_lap = None

    # ------------------------------------------------------------- mémoire partagée
    def _open(self) -> bool:
        if self.ptr:
            return True
        if sys.platform != "win32":
            return False
        import ctypes.wintypes as W
        k32 = C.WinDLL("kernel32", use_last_error=True)
        k32.OpenFileMappingW.restype = W.HANDLE
        k32.OpenFileMappingW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
        k32.MapViewOfFile.restype = C.c_void_p
        k32.MapViewOfFile.argtypes = [W.HANDLE, W.DWORD, W.DWORD, W.DWORD, C.c_size_t]
        h = k32.OpenFileMappingW(4, False, MAP_NAME)
        if not h:
            return False
        p = k32.MapViewOfFile(h, 4, 0, 0, 0)
        if not p:
            return False
        self.ptr = p
        return True

    def _header(self) -> Header:
        return Header.from_buffer_copy(C.string_at(self.ptr, C.sizeof(Header)))

    def _values(self, h: Header, names=None) -> dict:
        if self.nvars != h.numVars:
            raw = C.string_at(self.ptr + h.varHeaderOffset, h.numVars * C.sizeof(VarHeader))
            sz = C.sizeof(VarHeader)
            self.vars = {}
            for i in range(h.numVars):
                v = VarHeader.from_buffer_copy(raw[i * sz:(i + 1) * sz])
                self.vars[v.name.decode("latin-1")] = (v.type, v.offset, v.count)
            self.nvars = h.numVars
        for _ in range(3):
            i = max(range(h.numBuf), key=lambda k: h.varBuf[k].tickCount)
            b = h.varBuf[i]
            raw = C.string_at(self.ptr + b.bufOffset, h.bufLen)
            h2 = self._header()
            if h2.varBuf[i].tickCount == b.tickCount:
                break
            h = h2
        out = {"_tick": b.tickCount}
        for name in (names or self.vars):
            spec = self.vars.get(name)
            if not spec:
                continue
            t, off, n = spec
            ct, size = TYPES.get(t, (C.c_float, 4))
            arr = (ct * n).from_buffer_copy(raw[off:off + size * n])
            vals = list(arr)
            out[name] = vals[0] if n == 1 else vals
        return out

    def _session_info(self, h: Header) -> dict:
        if h.sessionInfoUpdate != self.info_v:
            self.info_v = h.sessionInfoUpdate
            txt = C.string_at(self.ptr + h.sessionInfoOffset, h.sessionInfoLen).split(b"\0", 1)[0]
            try:
                self.info = parse_session(txt.decode("latin-1", "replace"))
            except Exception:
                self.info = {}
        return self.info

    def alive(self) -> bool:
        if not self._open():
            return False
        try:
            h = self._header()
        except Exception:
            return False
        if not (h.status & 1):
            return False
        tick = max(h.varBuf[k].tickCount for k in range(max(1, min(4, h.numBuf))))
        now = time.time()
        if tick != self._last_tick:
            self._last_tick, self._tick_t = tick, now
        return now - self._tick_t < 5

    def close(self) -> None:
        pass

    # ------------------------------------------------------------- lectures rapides
    FAST = ["LapCompleted", "LapDistPct", "OnPitRoad", "Speed", "LatAccel", "SteeringWheelAngle", "Throttle", "Brake",
            "VelocityX", "VelocityY", "Yaw", "YawRate", "SessionTime", "dcBrakeBias", "dcABS", "dcTractionControl",
            "IsOnTrack", "CarLeftRight"]

    def fast_sample(self) -> dict | None:
        if not self.alive():
            return None
        d = self._values(self._header(), self.FAST)
        if not d.get("IsOnTrack"):
            return None
        v = max(0.0, float(d.get("Speed") or 0))
        f = float(d.get("LapDistPct") or 0) % 1
        pits = bool(d.get("OnPitRoad"))
        self.line.step(f, float(d.get("VelocityX") or 0), float(d.get("VelocityY") or 0), float(d.get("Yaw") or 0),
                       float(d.get("SessionTime") or 0), pits)
        # sous / survirage estimés : rotation de la voiture comparée à ce que demande le volant
        sw, r, lat = float(d.get("SteeringWheelAngle") or 0), float(d.get("YawRate") or 0), float(d.get("LatAccel") or 0)
        bal = 0.0
        if v > 12 and abs(r) > 0.02:
            if abs(lat) < 4 and abs(sw) > 0.05:          # virage léger : la voiture fait ce que demande le volant
                k = sw * v / r
                if 5 < k < 150:
                    self._k.append(k)
                    if len(self._k) > 600:
                        self._k = self._k[-600:]
            if len(self._k) > 50:
                kk = sorted(self._k)[len(self._k) // 2]
                want = sw * v / kk                        # rotation que le volant demande (rad/s)
                sgn = 1 if want * r > 0 else -1
                bal = WHEELBASE / v * (abs(want) - sgn * abs(r))   # > 0 : tourne moins que demandé = sous-virage
        base = 0.05 + max(0.0, -bal)
        front = max(0.0, base + bal)
        bias = d.get("dcBrakeBias")
        if bias:
            bias = float(bias) / 100 if bias > 1 else float(bias)
        return {
            "lap": int(d.get("LapCompleted") or 0), "f": f, "pits": pits, "speed": v, "lat": lat, "steer": sw,
            "thr": float(d.get("Throttle") or 0), "brk": float(d.get("Brake") or 0),
            "alpha": [front, front, base, base], "ratio": [0.0] * 4,
            "temps": [[0.0] * 3 for _ in range(4)], "opt": 0.0, "ride": [0.05, 0.05],
            "tc": d.get("dcTractionControl") or None, "abs": d.get("dcABS") or None,
            "bias": (1 - bias) if bias and 0.2 < bias < 0.8 else None, "farb": None, "rarb": None, "btemp": None,
        }

    def spot_sample(self) -> dict | None:
        if not self.alive():
            return None
        d = self._values(self._header(), ["CarLeftRight", "IsOnTrack", "Speed"])
        if not d.get("IsOnTrack"):
            return None
        # 0 rien, 1 libre, 2 à gauche, 3 à droite, 4 des deux côtés, 5 deux à gauche, 6 deux à droite
        return {"lr": int(d.get("CarLeftRight") or 0), "speed": float(d.get("Speed") or 0),
                "me": (0.0, 0.0), "others": [], "t": time.monotonic()}

    # ------------------------------------------------------------- lecture complète
    def read(self):
        from telemetry import Snapshot
        s = Snapshot()
        if not self.alive():
            return s
        h = self._header()
        info = self._session_info(h)
        d = self._values(h)
        s.connected = True
        s.game = "iracing"
        if not d.get("IsOnTrack"):
            return s
        s.on_track = True

        wk = info.get("WeekendInfo", {})
        name = wk.get("TrackDisplayName") or wk.get("TrackName") or "iRacing"
        cfg = wk.get("TrackConfigName", "")
        s.track = name + (f" {cfg}" if cfg and cfg.lower() not in ("full course", "grand prix", "gp", "") else "") + " (iRacing)"
        s.track_len = _num(wk.get("TrackLength")) * 1000
        s.oval = "oval" in (wk.get("TrackType", "") + " " + wk.get("Category", "")).lower()
        s.fixed_setup = wk.get("IsFixedSetup", "0").strip() == "1"
        lim = wk.get("TrackPitSpeedLimit", "")
        if _num(lim) > 0:
            v = _num(lim)
            s.pit_limit = v / 3.6 if "kph" in lim.lower() else v * 0.44704 if "mph" in lim.lower() else v / 3.6

        di = info.get("DriverInfo", {})
        drivers = {int(_num(x.get("CarIdx"), -1)): x for x in di.get("_Drivers", [])}
        me = int(d.get("PlayerCarIdx") or _num(di.get("DriverCarIdx"), 0))
        mine = drivers.get(me, {})
        s.car = mine.get("CarScreenName", "")
        s.car_class = mine.get("CarClassShortName") or s.car or "iRacing"
        s.driver = mine.get("UserName", "")

        snum = int(d.get("SessionNum") or 0)
        sessions = {int(_num(x.get("SessionNum"), -1)): x for x in info.get("SessionInfo", {}).get("_Sessions", [])}
        sess = sessions.get(snum, {})
        s.session, s.session_code = _session(sess.get("SessionType", ""))
        # durée de la course du week-end, connue dès les essais (pour le briefing essence)
        race = next((x for x in sessions.values() if "race" in x.get("SessionType", "").lower()), None)
        if race:
            sl, st = race.get("SessionLaps", ""), race.get("SessionTime", "")
            if sl.isdigit() and int(sl) > 0:
                s.race_laps_known = int(sl)
            elif "sec" in st and _num(st) > 0:
                s.race_min_known = int(round(_num(st) / 60))
        key = (s.track, snum, wk.get("SessionID"), wk.get("SubSessionID"))
        if key != self._sess:
            self._sess, self._stops, self._done_lap = key, 0, None
            if self.line.track != s.track:
                self.line.reset(s.track)

        state = int(d.get("SessionState") or 0)   # 1 dans la voiture, 2 chauffe, 3 tour de formation, 4 course, 5 damier, 6 fin
        flags = int(d.get("SessionFlags") or 0)
        s.game_phase = 8 if state >= 5 else 4 if state in (1, 2, 3) else 6 if flags & (F_CAUTION | F_CAUTION_WAVING) else 5
        s.yellow = bool(flags & (F_YELLOW | F_YELLOW_WAVING | F_CAUTION | F_CAUTION_WAVING))   # caution = drapeau jaune
        s.one_to_green = bool(flags & 0x0200)
        s.elapsed = float(d.get("SessionTime") or 0)
        rem = float(d.get("SessionTimeRemain") or -1)
        total_laps = int(d.get("SessionLapsTotal") or 32767)
        if 0 < total_laps < 32767 and s.session == "course":
            s.max_laps = total_laps
        elif 0 <= rem < 7 * 24 * 3600:
            s.time_left = rem

        s.laps_done = max(0, int(d.get("LapCompleted") or 0))      # -1 avant le départ
        s.lap_frac = float(d.get("LapDistPct") or 0) % 1
        lt = float(d.get("LapLastLapTime") or 0)
        bt = float(d.get("LapBestLapTime") or 0)
        s.last_lap = lt if lt > 0 else None
        s.best_lap = bt if bt > 0 else None
        cur = float(d.get("LapCurrentLapTime") or 0)
        s.lap_time = cur if 0 <= cur < 3600 else None
        s.position = int(d.get("PlayerCarPosition") or 0)
        s.class_position = int(d.get("PlayerCarClassPosition") or 0)
        if s.game_phase == 8 and s.session == "course":
            if self._done_lap is None:
                self._done_lap = s.laps_done
            if s.laps_done > self._done_lap or state >= 6:
                s.finish_status = 1

        s.fuel = float(d.get("FuelLevel") or 0)
        s.fuel_capacity = _num(di.get("DriverCarFuelMaxLtr")) * (_num(di.get("DriverCarMaxFuelPct"), 1.0) or 1.0)
        s.energy = None
        s.speed = max(0.0, float(d.get("Speed") or 0))
        ew = int(d.get("EngineWarnings") or 0)
        s.limiter = bool(ew & PIT_LIMITER)

        # pneus : iRacing ne les met à jour qu'au stand -> usure du dernier arrêt, pas de température
        wear = []
        for w in ("LF", "RF", "LR", "RR"):
            vals = [d.get(f"{w}wear{p}") for p in "LMR"]
            vals = [float(x) for x in vals if x is not None]
            wear.append(sum(vals) / len(vals) if vals else 1.0)
        if all(0 < x <= 1 for x in wear):
            self._wear = wear
        s.tyre_wear = list(self._wear)
        unknown = [-273.0] * 4
        s.tyre_temp, s.tyre_inner_temp, s.tyre_carcass_temp, s.tyre_surface_temp = (list(unknown) for _ in range(4))
        s.brake_temp = list(unknown)
        s.tyre_pressure = [float(d.get(f"{w}coldPressure") or 0) for w in ("LF", "RF", "LR", "RR")]
        tyres = {int(_num(x.get("TireIndex"), -1)): x.get("TireCompoundType", "") for x in di.get("_DriverTires", [])}
        s.compound = tyres.get(int(d.get("PlayerTireCompound") or 0), "")
        s.wet_tyres = "wet" in s.compound.lower() or "rain" in s.compound.lower()
        s.tyre_opt = 0.0

        # stands
        s.in_pits = bool(d.get("OnPitRoad"))
        if "PitsOpen" in d:
            s.pits_open = bool(d.get("PitsOpen"))
        stall = bool(d.get("PlayerCarInPitStall"))
        s.pit_state = 3 if stall else 2 if s.in_pits else 0
        if stall and not self._was_stall:
            self._stops += 1
        self._was_stall = stall
        s.pit_stops = self._stops
        cf = d.get("CarIdxSessionFlags") or []
        s.penalties = 1 if me < len(cf) and int(cf[me]) & F_BLACK else 0
        s.blue = bool(me < len(cf) and int(cf[me]) & 0x0020)        # drapeau bleu montré à ta voiture

        # météo
        s.air_temp = float(d.get("AirTemp") or 0)
        s.track_temp = float(d.get("TrackTempCrew") or d.get("TrackTemp") or 0)
        s.raining = min(1.0, max(0.0, float(d.get("Precipitation") or 0)))
        wet = int(d.get("TrackWetness") or 0)        # 0 inconnu, 1 sec … 7 inondé
        s.wetness = max(0.0, (wet - 1) / 6) if wet else 0.0

        try:
            s.car_state = {"limiter": s.limiter, "tc": d.get("dcTractionControl"), "abs": d.get("dcABS"),
                           "bias": d.get("dcBrakeBias"), "rpm": int(d.get("RPM") or 0)}
        except Exception:
            s.car_state = {}

        # toutes les voitures : progression dans le tour (fournie par iRacing), position sur le tracé appris
        pos = d.get("CarIdxPosition") or []
        cpos = d.get("CarIdxClassPosition") or []
        lapd = d.get("CarIdxLapDistPct") or []
        laps = d.get("CarIdxLapCompleted") or []
        pit = d.get("CarIdxOnPitRoad") or []
        best = d.get("CarIdxBestLapTime") or []
        last = d.get("CarIdxLastLapTime") or []
        est = d.get("CarIdxEstTime") or []
        classes: list = []
        now = time.monotonic()
        my_class = mine.get("CarClassID")
        L = s.track_len
        same = []
        for i, drv in drivers.items():
            if i < 0 or i >= len(lapd) or drv.get("CarIsPaceCar") == "1" or drv.get("IsSpectator") == "1":
                continue
            f = float(lapd[i])
            if f < 0:                       # pas en piste (garage, déconnecté)
                continue
            cls = drv.get("CarClassShortName") or drv.get("CarScreenName", "")
            if cls not in classes:
                classes.append(cls)
            pf = self._prev_f.get(i)
            spd = (((f - pf[0]) % 1) * L / max(1e-3, now - pf[1])) if pf and L else 0.0
            if spd > 120:
                spd = 0.0
            self._prev_f[i] = (f, now)
            xy = self.line.at(f)
            b = float(best[i]) if i < len(best) and best[i] > 0 else None
            c = {"x": xy[0] if xy else 0.0, "z": xy[1] if xy else 0.0, "nomap": xy is None, "id": i, "spd": spd,
                 "off": False, "f": f, "s": 0, "c": classes.index(cls), "cls": cls,
                 "p": int(pos[i]) if i < len(pos) else 0, "me": i == me,
                 "pits": bool(pit[i]) if i < len(pit) else False, "rel": "", "best": b,
                 "name": drv.get("UserName", "")}
            s.cars.append(c)
            if drv.get("CarClassID") == my_class:
                same.append((int(cpos[i]) if i < len(cpos) and cpos[i] > 0 else 999, i, drv))
        s.num_cars = len(s.cars)
        if not s.position and s.session == "course":    # grille : résultat des qualifs (0 = pole)
            for r in info.get("QualifyResultsInfo", {}).get("_Results", []):
                if int(_num(r.get("CarIdx"), -1)) == me:
                    s.position = int(_num(r.get("Position"), -1)) + 1
                    s.class_position = int(_num(r.get("ClassPosition"), -1)) + 1 or s.position
        if not s.position:              # avant le départ iRacing donne 0 : on classe d'après la piste
            s.pos_guess = True
            order = sorted((c for c in s.cars), key=lambda c: -((int(laps[c["id"]]) if c["id"] < len(laps) else 0) + c["f"]))
            s.position = next((k + 1 for k, c in enumerate(order) if c["me"]), 0)
        if not s.class_position:
            s.class_position = s.position

        # écarts : temps estimé pour arriver là où est chaque voiture (CarIdxEstTime), même principe que LMU
        lap_ref = s.best_lap or s.last_lap or _num(di.get("DriverCarEstLapTime"), 0) or None

        def gap_to(i):
            if i >= len(est) or me >= len(est) or not lap_ref:
                return None
            g = (float(est[i]) - float(est[me])) % lap_ref
            return g                                    # temps pour que TOI tu arrives où elle est (devant)

        same.sort()
        k_me = next((k for k, x in enumerate(same) if x[1] == me), None)

        def other(i, drv):
            return {"name": drv.get("UserName", ""), "car": drv.get("CarScreenName", ""),
                    "laps": int(laps[i]) if i < len(laps) else 0, "place": int(pos[i]) if i < len(pos) else 0,
                    "last_lap": float(last[i]) if i < len(last) and last[i] > 0 else None, "sectors": None,
                    "in_pits": bool(pit[i]) if i < len(pit) else False}

        if k_me is not None and s.session == "course":
            my_laps = (int(laps[me]) if me < len(laps) else 0) + s.lap_frac
            for k, (cp, i, drv) in enumerate(same):
                if i == me:
                    continue
                o = other(i, drv)
                o["cpos"] = k + 1
                their = (int(laps[i]) if i < len(laps) else 0) + float(lapd[i])
                diff = their - my_laps              # > 0 : devant toi (en tours)
                o["gap"] = diff * lap_ref if lap_ref else None
                o["best"] = float(best[i]) if i < len(best) and best[i] > 0 else None
                s.rivals.append(o)
            if k_me > 0:
                cp, i, drv = same[k_me - 1]
                s.ahead = other(i, drv)
                r = next((o for o in s.rivals if o["cpos"] == k_me), None)
                s.gap_class_ahead = r["gap"] if r and r["gap"] and r["gap"] > 0 else None
            if k_me + 1 < len(same):
                cp, i, drv = same[k_me + 1]
                s.behind = other(i, drv)
                r = next((o for o in s.rivals if o["cpos"] == k_me + 2), None)
                s.gap_class_behind = -r["gap"] if r and r["gap"] and r["gap"] < 0 else None
            ahead_id = same[k_me - 1][1] if k_me > 0 else None
            behind_id = same[k_me + 1][1] if k_me + 1 < len(same) else None
            for c in s.cars:
                c["rel"] = "ahead" if c["id"] == ahead_id else "behind" if c["id"] == behind_id else ""

        # voiture juste devant / derrière sur la piste (toutes catégories)
        ahead_t, behind_t = [], []
        for c in s.cars:
            if c["me"] or c["pits"]:
                continue
            g = gap_to(c["id"])
            if g is None:
                continue
            (ahead_t if g < lap_ref / 2 else behind_t).append(g if g < lap_ref / 2 else lap_ref - g)
        # rangement derrière la pace car (départ, caution) : ta file et la voiture à suivre
        prow, pline, pfl = d.get("CarIdxPaceRow") or [], d.get("CarIdxPaceLine") or [], d.get("CarIdxPaceFlags") or []
        if me < len(prow) and prow[me] >= 0 and me < len(pline) and pline[me] >= 0:
            row, line = int(prow[me]), int(pline[me])
            follow = "pace"
            if row > 0:
                for i in range(min(len(prow), len(pline))):
                    if i != me and int(prow[i]) == row - 1 and int(pline[i]) == line:
                        follow = drivers.get(i, {}).get("CarNumber", "") or "?"
                        break
            s.pace = {"row": row, "line": line, "flags": int(pfl[me]) if me < len(pfl) else 0, "follow": follow}
        s.gap_ahead = min(ahead_t) if ahead_t else None
        s.gap_behind = min(behind_t) if behind_t else None
        return s
