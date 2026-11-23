"""
Lecture des données d'Automobilista 2 (mémoire partagée « Project CARS 2 », nom "$pcars2$", version 14).

Dans le jeu : Options → Système → Mémoire partagée → « Project CARS 2 » (sinon rien n'est partagé).

AMS2Source renvoie le même Snapshot que LMUSource : la stratégie essence, les écarts, les annonces de trafic,
le spotter, la radio et les références de tour fonctionnent sans savoir de quel jeu viennent les données.

AMS2 donne beaucoup de choses (noms des pilotes, positions, usure et températures des pneus et des freins,
dégâts, drapeaux…). Ce qu'il ne donne pas : l'énergie virtuelle, la position sur la largeur de la piste,
l'écart exact au leader (calculé ici avec la progression de chaque voiture) ; le menu des stands ne se règle pas.
"""

from __future__ import annotations

import ctypes as C
import math
import sys
import time

MAP_NAME = "$pcars2$"
SM_VERSION = 14
NAME = 64           # STRING_LENGTH_MAX
PARTS = 64          # STORED_PARTICIPANTS_MAX
COMPOUND = 40       # TYRE_COMPOUND_NAME_LENGTH_MAX

f32, i32, u32, b8, ch = C.c_float, C.c_int32, C.c_uint32, C.c_bool, C.c_char
V3 = f32 * 3
W4 = f32 * 4


class Participant(C.Structure):
    _fields_ = [("mIsActive", b8), ("mName", ch * NAME), ("mWorldPosition", V3), ("mCurrentLapDistance", f32),
                ("mRacePosition", u32), ("mLapsCompleted", u32), ("mCurrentLap", u32), ("mCurrentSector", i32)]


# Champs dans l'ordre exact de SharedMemory.h (Madness / Project CARS 2, version 14, alignement naturel MSVC)
class Shared(C.Structure):
    _fields_ = [
        ("mVersion", u32), ("mBuildVersionNumber", u32), ("mGameState", u32), ("mSessionState", u32), ("mRaceState", u32),
        ("mViewedParticipantIndex", i32), ("mNumParticipants", i32), ("mParticipantInfo", Participant * PARTS),
        ("mUnfilteredThrottle", f32), ("mUnfilteredBrake", f32), ("mUnfilteredSteering", f32), ("mUnfilteredClutch", f32),
        ("mCarName", ch * NAME), ("mCarClassName", ch * NAME), ("mLapsInEvent", u32),
        ("mTrackLocation", ch * NAME), ("mTrackVariation", ch * NAME), ("mTrackLength", f32), ("mNumSectors", i32),
        ("mLapInvalidated", b8), ("mBestLapTime", f32), ("mLastLapTime", f32), ("mCurrentTime", f32),
        ("mSplitTimeAhead", f32), ("mSplitTimeBehind", f32), ("mSplitTime", f32), ("mEventTimeRemaining", f32),
        ("mPersonalFastestLapTime", f32), ("mWorldFastestLapTime", f32),
        ("mCurrentSector1Time", f32), ("mCurrentSector2Time", f32), ("mCurrentSector3Time", f32),
        ("mFastestSector1Time", f32), ("mFastestSector2Time", f32), ("mFastestSector3Time", f32),
        ("mPersonalFastestSector1Time", f32), ("mPersonalFastestSector2Time", f32), ("mPersonalFastestSector3Time", f32),
        ("mWorldFastestSector1Time", f32), ("mWorldFastestSector2Time", f32), ("mWorldFastestSector3Time", f32),
        ("mHighestFlagColour", u32), ("mHighestFlagReason", u32), ("mPitMode", u32), ("mPitSchedule", u32), ("mCarFlags", u32),
        ("mOilTempCelsius", f32), ("mOilPressureKPa", f32), ("mWaterTempCelsius", f32), ("mWaterPressureKPa", f32),
        ("mFuelPressureKPa", f32), ("mFuelLevel", f32), ("mFuelCapacity", f32), ("mSpeed", f32), ("mRpm", f32), ("mMaxRPM", f32),
        ("mBrake", f32), ("mThrottle", f32), ("mClutch", f32), ("mSteering", f32), ("mGear", i32), ("mNumGears", i32),
        ("mOdometerKM", f32), ("mAntiLockActive", b8), ("mLastOpponentCollisionIndex", i32), ("mLastOpponentCollisionMagnitude", f32),
        ("mBoostActive", b8), ("mBoostAmount", f32),
        ("mOrientation", V3), ("mLocalVelocity", V3), ("mWorldVelocity", V3), ("mAngularVelocity", V3),
        ("mLocalAcceleration", V3), ("mWorldAcceleration", V3), ("mExtentsCentre", V3),
        ("mTyreFlags", u32 * 4), ("mTerrain", u32 * 4), ("mTyreY", W4), ("mTyreRPS", W4), ("mTyreSlipSpeed", W4),
        ("mTyreTemp", W4), ("mTyreGrip", W4), ("mTyreHeightAboveGround", W4), ("mTyreLateralStiffness", W4),
        ("mTyreWear", W4), ("mBrakeDamage", W4), ("mSuspensionDamage", W4), ("mBrakeTempCelsius", W4),
        ("mTyreTreadTemp", W4), ("mTyreLayerTemp", W4), ("mTyreCarcassTemp", W4), ("mTyreRimTemp", W4), ("mTyreInternalAirTemp", W4),
        ("mCrashState", u32), ("mAeroDamage", f32), ("mEngineDamage", f32),
        ("mAmbientTemperature", f32), ("mTrackTemperature", f32), ("mRainDensity", f32), ("mWindSpeed", f32),
        ("mWindDirectionX", f32), ("mWindDirectionY", f32), ("mCloudBrightness", f32),
        ("mSequenceNumber", u32), ("mWheelLocalPositionY", W4), ("mSuspensionTravel", W4), ("mSuspensionVelocity", W4),
        ("mAirPressure", W4), ("mEngineSpeed", f32), ("mEngineTorque", f32), ("mWings", f32 * 2), ("mHandBrake", f32),
        ("mCurrentSector1Times", f32 * PARTS), ("mCurrentSector2Times", f32 * PARTS), ("mCurrentSector3Times", f32 * PARTS),
        ("mFastestSector1Times", f32 * PARTS), ("mFastestSector2Times", f32 * PARTS), ("mFastestSector3Times", f32 * PARTS),
        ("mFastestLapTimes", f32 * PARTS), ("mLastLapTimes", f32 * PARTS), ("mLapsInvalidated", b8 * PARTS),
        ("mRaceStates", u32 * PARTS), ("mPitModes", u32 * PARTS), ("mOrientations", V3 * PARTS), ("mSpeeds", f32 * PARTS),
        ("mCarNames", (ch * NAME) * PARTS), ("mCarClassNames", (ch * NAME) * PARTS),
        ("mEnforcedPitStopLap", i32), ("mTranslatedTrackLocation", ch * NAME), ("mTranslatedTrackVariation", ch * NAME),
        ("mBrakeBias", f32), ("mTurboBoostPressure", f32), ("mTyreCompound", (ch * COMPOUND) * 4),
        ("mPitSchedules", u32 * PARTS), ("mHighestFlagColours", u32 * PARTS), ("mHighestFlagReasons", u32 * PARTS),
        ("mNationalities", u32 * PARTS), ("mSnowDensity", f32), ("mSessionDuration", f32), ("mSessionAdditionalLaps", i32),
        ("mTyreTempLeft", W4), ("mTyreTempCenter", W4), ("mTyreTempRight", W4), ("mDrsState", u32), ("mRideHeight", W4),
        ("mJoyPad0", u32), ("mDPad", u32), ("mAntiLockSetting", i32), ("mTractionControlSetting", i32),
        ("mErsDeploymentMode", i32), ("mErsAutoModeEnabled", b8), ("mClutchTemp", f32), ("mClutchWear", f32),
        ("mClutchOverheated", b8), ("mClutchSlipping", b8), ("mYellowFlagState", i32), ("mSessionIsPrivate", b8),
        ("mLaunchStage", i32),
    ]


# états du jeu et de la séance (SharedMemory.h)
GAME_PLAYING, GAME_PAUSED, GAME_MENU_TICKING = 2, 3, 4
SESS_PRACTICE, SESS_TEST, SESS_QUALIFY, SESS_FORMATION, SESS_RACE, SESS_TIME_ATTACK = 1, 2, 3, 4, 5, 6
RACE_NOT_STARTED, RACE_RACING, RACE_FINISHED, RACE_DQ, RACE_RETIRED, RACE_DNF = 1, 2, 3, 4, 5, 6
FLAG_BLUE, FLAG_YELLOW, FLAG_DOUBLE_YELLOW, FLAG_BLACK_WHITE, FLAG_MEATBALL, FLAG_BLACK, FLAG_CHEQUERED = 2, 6, 7, 8, 9, 10, 11
PIT_NONE, PIT_IN, PIT_STOPPED, PIT_OUT, PIT_GARAGE, PIT_OUT_GARAGE = 0, 1, 2, 3, 4, 5
CAR_LIMITER, CAR_HEADLIGHT = 1 << 3, 1 << 0
SCHED_DRIVE_THROUGH, SCHED_STOP_GO = 5, 6
TERRAIN_RUMBLE, TERRAIN_EXIT_RUMBLE = 10, 25


def _txt(b) -> str:
    try:
        return bytes(b).split(b"\0", 1)[0].decode("utf-8", "replace").strip()
    except Exception:
        return ""


def _xz(v) -> tuple[float, float]:
    """Coordonnées AMS2 -> repère d'Apex Radio (celui de LMU). AMS2 : x vers l'est, y en haut, z vers le nord
    (d'après les cartes GPS des circuits), donc même sens de rotation que LMU : pas d'axe à inverser
    (contrairement à AC EVO). À vérifier au premier test : si le spotter dit « à droite » pour une voiture
    à gauche, il faut mettre -x ici."""
    return float(v[0]), float(v[2])


class _Page:
    """La mémoire partagée de Windows, ouverte en lecture seule."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.ptr = None

    def open(self) -> bool:
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
        h = k32.OpenFileMappingW(4, False, self.name)          # FILE_MAP_READ
        if not h:
            return False
        p = k32.MapViewOfFile(h, 4, 0, 0, 0)
        if not p:
            return False
        self.ptr = p
        return True

    def read(self) -> Shared | None:
        """Copie cohérente : le jeu rend mSequenceNumber impair pendant qu'il écrit."""
        for _ in range(5):
            sm = Shared.from_buffer_copy(C.string_at(self.ptr, C.sizeof(Shared)))
            if sm.mSequenceNumber % 2 == 0:
                seq = C.c_uint32.from_address(self.ptr + Shared.mSequenceNumber.offset).value
                if seq == sm.mSequenceNumber:
                    return sm
            time.sleep(0.002)
        return sm


def _session(code: int) -> tuple[str, int]:
    if code == SESS_RACE or code == SESS_FORMATION:
        return "course", 10
    if code == SESS_QUALIFY:
        return "qualif", 5
    return "essais", 0


class AMS2Source:
    """Lecture en direct d'Automobilista 2."""

    game = "ams2"

    def __init__(self) -> None:
        self.page = _Page(MAP_NAME)
        self._t0 = time.monotonic()
        self._sess_key = None
        self._stops = 0
        self._was_stopped = False
        self._seq = None
        self._seq_t = 0.0
        self._version_said = False
        self._sm = None
        self._sm_t = 0.0
        self._radius = [None] * 4      # rayon effectif de chaque roue (m), appris en roue libre
        self._rad_n = 0

    def _get(self) -> Shared | None:
        if not self.page.open():
            return None
        now = time.monotonic()
        if self._sm is not None and now - self._sm_t < 0.015:    # plusieurs lectures dans la même boucle
            return self._sm
        try:
            sm = self.page.read()
        except Exception:
            return None
        self._sm, self._sm_t = sm, now
        if not self._version_said and sm.mVersion:
            self._version_said = True
            note = "" if sm.mVersion == SM_VERSION else f" (Apex attend la version {SM_VERSION} : certaines infos peuvent être fausses)"
            print(f"  AMS2 : mémoire partagée version {sm.mVersion}, build {sm.mBuildVersionNumber}{note}")
        return sm

    def alive(self) -> bool:
        """Le jeu tourne et partage ses données (la mémoire reste après la fermeture : on vérifie que ça bouge)."""
        sm = self._get()
        if sm is None or sm.mVersion == 0:
            return False
        now = time.time()
        if sm.mSequenceNumber != self._seq:
            self._seq, self._seq_t = sm.mSequenceNumber, now
        return sm.mGameState != 0 and now - self._seq_t < 10

    def close(self) -> None:
        pass

    @staticmethod
    def _me(sm) -> int | None:
        i = sm.mViewedParticipantIndex
        return i if 0 <= i < min(PARTS, max(0, sm.mNumParticipants)) else None

    def _playing(self, sm) -> bool:
        return sm.mGameState in (GAME_PLAYING, GAME_PAUSED, GAME_MENU_TICKING) and sm.mSessionState != 0

    def spot_sample(self) -> dict | None:
        sm = self._get()
        if sm is None or not self._playing(sm):
            return None
        pi = self._me(sm)
        if pi is None:
            return None
        n = min(PARTS, max(0, sm.mNumParticipants))
        me = _xz(sm.mParticipantInfo[pi].mWorldPosition)
        others = [_xz(sm.mParticipantInfo[i].mWorldPosition) for i in range(n)
                  if i != pi and sm.mParticipantInfo[i].mIsActive and sm.mPitModes[i] not in (PIT_STOPPED, PIT_GARAGE)]
        return {"me": me, "others": others, "t": time.monotonic() - self._t0}

    def fast_sample(self) -> dict | None:
        """Dynamique de ta voiture (~50 fois/s) pour l'analyse du pilotage. Mêmes clés et unités que LMU."""
        sm = self._get()
        if sm is None or not self._playing(sm):
            return None
        pi = self._me(sm)
        if pi is None:
            return None
        part = sm.mParticipantInfo[pi]
        L = sm.mTrackLength or 0
        speed = max(0.0, float(sm.mSpeed))
        alpha, ratio = self._slip(sm, speed)
        tread = [float(x) - 273.15 for x in sm.mTyreTreadTemp]
        temps = [[float(sm.mTyreTempLeft[k]), float(sm.mTyreTempCenter[k]), float(sm.mTyreTempRight[k])] for k in range(4)]
        if not any(any(t) for t in temps):
            temps = [[t, t, t] for t in tread]
        bias = float(sm.mBrakeBias)
        return {
            "lap": int(part.mLapsCompleted), "f": min(1.0, max(0.0, part.mCurrentLapDistance / L)) if L else 0.0,
            "pits": sm.mPitMode != PIT_NONE,
            "speed": speed,
            "lat": float(sm.mLocalAcceleration[0]),
            "steer": float(sm.mSteering), "thr": float(sm.mThrottle), "brk": float(sm.mBrake),
            "alpha": alpha,
            "ratio": ratio,
            "temps": temps, "opt": 85.0,
            "ride": [float(sm.mRideHeight[0]) / 100, float(sm.mRideHeight[2]) / 100],      # cm -> m
            "tc": float(sm.mTractionControlSetting), "abs": float(sm.mAntiLockSetting),
            "bias": bias if 0.2 < bias < 0.8 else None,     # part du freinage à l'arrière (0.34 = 66 % à l'avant)
            "farb": None, "rarb": None,
            "btemp": [float(x) for x in sm.mBrakeTempCelsius],
            "curb": sum(1 for t in sm.mTerrain if int(t) in (TERRAIN_RUMBLE, TERRAIN_EXIT_RUMBLE)),
        }

    LEARN = 100      # échantillons en roue libre avant de faire confiance au rayon des roues

    def _slip(self, sm, speed: float) -> tuple[list, list]:
        """AMS2 ne donne ni l'angle de dérive ni le taux de glissement des pneus, seulement une vitesse de glisse
        (qui mélange patinage et dérive) et la vitesse de rotation des roues. On apprend le rayon de chaque roue
        en roue libre (ni gaz ni frein, en ligne droite), puis : patinage/blocage = rotation × rayon − vitesse,
        dérive = le reste de la glisse. Tant que le rayon n'est pas appris : rien (pas de faux survirage)."""
        rps = [abs(float(x)) for x in sm.mTyreRPS]
        if speed > 15 and sm.mThrottle < 0.05 and sm.mBrake < 0.05 and abs(sm.mLocalAcceleration[0]) < 2 and min(rps) > 1:
            for i in range(4):
                r = speed / rps[i]
                self._radius[i] = r if self._radius[i] is None else self._radius[i] * 0.98 + r * 0.02
            self._rad_n += 1
        if self._rad_n < self.LEARN or speed < 5:
            return [0.0] * 4, [0.0] * 4
        alpha, ratio = [], []
        for i in range(4):
            lg = rps[i] * self._radius[i] - speed
            slip = abs(float(sm.mTyreSlipSpeed[i]))
            lat = math.sqrt(max(0.0, slip * slip - lg * lg))
            alpha.append(min(0.5, math.atan2(lat, max(speed, 1.0))))
            ratio.append(lg / max(speed, 1.0))
        return alpha, ratio

    def read(self):
        from telemetry import Snapshot, split_sectors
        s = Snapshot()
        sm = self._get()
        if sm is None or not self.alive():
            return s
        s.connected = True
        s.game = "ams2"
        if not self._playing(sm):
            return s
        pi = self._me(sm)
        if pi is None:
            return s
        s.on_track = True
        n = min(PARTS, max(0, sm.mNumParticipants))
        mine = sm.mParticipantInfo[pi]

        loc = _txt(sm.mTranslatedTrackLocation) or _txt(sm.mTrackLocation)
        var = _txt(sm.mTranslatedTrackVariation) or _txt(sm.mTrackVariation)
        if var and var.lower().startswith(loc.lower()):
            name = var                                   # « Bathurst » + « Bathurst Historic 1983 »
        else:
            name = loc + (f" {var}" if var and var.lower() not in loc.lower() else "")
        s.track = name.strip() + " (AMS2)"
        s.car = _txt(sm.mCarName)
        s.car_class = _txt(sm.mCarClassName) or s.car or "AMS2"
        s.session, s.session_code = _session(sm.mSessionState)
        rs = sm.mRaceState
        s.game_phase = 4 if rs == RACE_NOT_STARTED or sm.mSessionState == SESS_FORMATION else 8 if rs >= RACE_FINISHED else 5
        if s.game_phase == 5 and 1 <= sm.mYellowFlagState <= 8:
            s.game_phase = 6          # voiture de sécurité / drapeau jaune général

        key = (loc, var, sm.mSessionState, s.car)
        if key != self._sess_key:
            self._sess_key = key
            self._t0 = time.monotonic()
            self._stops = 0
            self._was_stopped = False
            self._radius, self._rad_n = [None] * 4, 0      # autre voiture : autres roues
        s.elapsed = float(sm.mCurrentTime) if sm.mCurrentTime > 0 and sm.mSessionState != SESS_RACE else time.monotonic() - self._t0

        # durée : au temps (minutes + temps restant) ou au nombre de tours
        rem = float(sm.mEventTimeRemaining)
        if sm.mSessionDuration > 0 or (rem > 0 and not sm.mLapsInEvent):
            dur = float(sm.mSessionDuration) * 60
            if rem > 0:
                # la doc dit millisecondes, mais selon les versions c'est des secondes : on compare à la durée prévue
                if dur and rem > dur * 2:
                    rem /= 1000.0
                s.time_left = rem
            if s.session == "course" and dur:
                s.race_min_known = int(round(dur / 60))
        elif sm.mLapsInEvent > 0:
            s.max_laps = int(sm.mLapsInEvent) + max(0, int(sm.mSessionAdditionalLaps))

        L = float(sm.mTrackLength) or 0.0
        s.track_len = L
        s.laps_done = int(mine.mLapsCompleted)
        s.lap_frac = min(1.0, max(0.0, mine.mCurrentLapDistance / L)) if L else 0.0
        s.last_lap = float(sm.mLastLapTime) if 0 < sm.mLastLapTime < 3600 else None
        s.best_lap = float(sm.mBestLapTime) if 0 < sm.mBestLapTime < 3600 else None
        if not s.best_lap and 0 < sm.mPersonalFastestLapTime < 3600:
            s.best_lap = float(sm.mPersonalFastestLapTime)
        s.lap_time = float(sm.mCurrentTime) if 0 <= sm.mCurrentTime < 3600 else None
        s.position = int(mine.mRacePosition) or 1
        s.num_cars = sum(1 for i in range(n) if sm.mParticipantInfo[i].mIsActive) or n
        s.lap_invalid = bool(sm.mLapInvalidated)
        s1, s2, s3 = sm.mCurrentSector1Time, sm.mCurrentSector2Time, sm.mCurrentSector3Time
        if s1 > 0 and s2 > 0 and s3 > 0:
            s.sectors = [float(s1), float(s2), float(s3)]
        s.driver = _txt(mine.mName)
        s.finish_status = 1 if rs == RACE_FINISHED else 2 if rs in (RACE_RETIRED, RACE_DNF) else 3 if rs == RACE_DQ else 0

        # essence (AMS2 donne le niveau en fraction du réservoir)
        cap = float(sm.mFuelCapacity)
        s.fuel_capacity = cap
        s.fuel = float(sm.mFuelLevel) * cap if cap > 0 else float(sm.mFuelLevel)
        s.energy = None
        s.limiter = bool(sm.mCarFlags & CAR_LIMITER)
        s.speed = max(0.0, float(sm.mSpeed))

        # pneus et freins
        s.tyre_wear = [max(0.0, min(1.0, 1.0 - float(w))) for w in sm.mTyreWear]     # AMS2 : 0 = neuf
        surf = [float(x) for x in sm.mTyreTemp]
        tread = [float(x) - 273.15 if x > 100 else float(x) for x in sm.mTyreTreadTemp]
        carcass = [float(x) - 273.15 if x > 100 else float(x) for x in sm.mTyreCarcassTemp]
        s.tyre_surface_temp = surf
        s.tyre_temp = tread if any(t > -100 for t in tread) else surf
        s.tyre_inner_temp = s.tyre_temp
        s.tyre_carcass_temp = carcass if any(t > -100 for t in carcass) else s.tyre_temp
        # la doc dit PSI, mais le jeu envoie des kPa (≈150) : on convertit seulement si la valeur ressemble à des PSI
        s.tyre_pressure = [float(x) * 6.894757 if 0 < x < 60 else float(x) for x in sm.mAirPressure]
        s.brake_temp = [float(x) for x in sm.mBrakeTempCelsius]
        s.compound = _txt(sm.mTyreCompound[0])
        low = s.compound.lower()
        s.wet_tyres = any(k in low for k in ("wet", "rain", "chuva", "pluie", "inter"))
        s.tyre_opt = 60.0 if s.wet_tyres else 85.0
        s.flat = [not (int(f) & 2) and bool(int(f) & 1) for f in sm.mTyreFlags]        # attachée mais dégonflée
        s.wheel_off = [not (int(f) & 1) for f in sm.mTyreFlags]

        # dégâts : 0..1 -> 0/1/2 sur les 8 zones d'Apex (aéro partout, suspension = mécanique)
        def lvl(v):
            return 0 if v < 0.1 else 1 if v < 0.5 else 2
        a = lvl(float(sm.mAeroDamage))
        s.dents = [a, 0, a, 0, 0, 0, 0, 0]
        if max(float(x) for x in sm.mSuspensionDamage) > 0.15:
            s.dents[4] = 2

        # stands
        pm = int(sm.mPitMode)
        s.in_pits = pm in (PIT_IN, PIT_STOPPED, PIT_OUT, PIT_GARAGE, PIT_OUT_GARAGE)
        s.pit_state = {PIT_IN: 2, PIT_STOPPED: 3, PIT_OUT: 4}.get(pm, 1 if sm.mPitSchedule in (1, 2, 3, 4) else 0)
        if pm == PIT_STOPPED and not self._was_stopped:
            self._stops += 1
        self._was_stopped = pm == PIT_STOPPED
        s.pit_stops = self._stops
        s.penalties = 1 if sm.mPitSchedule in (SCHED_DRIVE_THROUGH, SCHED_STOP_GO) or sm.mHighestFlagColour == FLAG_BLACK else 0

        # météo et drapeaux
        s.air_temp = float(sm.mAmbientTemperature)
        s.track_temp = float(sm.mTrackTemperature)
        s.raining = max(0.0, min(1.0, float(sm.mRainDensity)))
        s.wetness = s.raining
        fl = int(sm.mHighestFlagColour)
        s.yellow = fl in (FLAG_YELLOW, FLAG_DOUBLE_YELLOW) or sm.mYellowFlagState > 0
        s.fcy_state = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 5, 7: 6}.get(int(sm.mYellowFlagState), 0)
        s.blue = fl == FLAG_BLUE
        s.pen_warning = fl == FLAG_BLACK_WHITE
        s.meatball = fl == FLAG_MEATBALL
        if fl in (FLAG_YELLOW, FLAG_DOUBLE_YELLOW) and 0 <= mine.mCurrentSector <= 2:
            s.yellow_sectors = [int(mine.mCurrentSector) + 1]     # jaune local : dans ton secteur

        try:
            s.car_state = {"lights": bool(sm.mCarFlags & CAR_HEADLIGHT), "limiter": s.limiter,
                           "tc": int(sm.mTractionControlSetting), "abs": int(sm.mAntiLockSetting), "rpm": int(sm.mRpm),
                           "bias": round(100 * (1 - sm.mBrakeBias), 1) if 0 < sm.mBrakeBias < 1 else None}
        except Exception:
            s.car_state = {}

        # toutes les voitures : AMS2 donne nom, catégorie, place, tours et distance dans le tour de chacune
        classes, rows = [], []
        for i in range(n):
            p = sm.mParticipantInfo[i]
            if not p.mIsActive:
                continue
            cls = _txt(sm.mCarClassNames[i]) or s.car_class
            if cls not in classes:
                classes.append(cls)
            x, z = _xz(p.mWorldPosition)
            f = min(1.0, max(0.0, p.mCurrentLapDistance / L)) if L else 0.0
            pits = int(sm.mPitModes[i]) in (PIT_IN, PIT_STOPPED, PIT_OUT, PIT_GARAGE, PIT_OUT_GARAGE)
            last = float(sm.mLastLapTimes[i]) if 0 < sm.mLastLapTimes[i] < 3600 else None
            best = float(sm.mFastestLapTimes[i]) if 0 < sm.mFastestLapTimes[i] < 3600 else None
            rows.append({"x": x, "z": z, "id": i, "spd": float(sm.mSpeeds[i]), "off": False, "f": f,
                         "s": max(0, min(2, int(p.mCurrentSector))), "c": classes.index(cls), "cls": cls,
                         "p": int(p.mRacePosition), "me": i == pi, "pits": pits, "rel": "", "best": best,
                         "name": _txt(p.mName), "dnf": int(sm.mRaceStates[i]) in (RACE_DQ, RACE_RETIRED, RACE_DNF),
                         "laps": int(p.mLapsCompleted) + f, "last": last, "car": _txt(sm.mCarNames[i])})
        s.cars = rows
        my_cls = _txt(sm.mCarClassNames[pi]) or s.car_class
        same = sorted((r for r in rows if r["cls"] == my_cls and r["p"] > 0), key=lambda r: r["p"])
        me_k = next((k for k, r in enumerate(same) if r["me"]), None)
        s.class_position = (me_k + 1) if me_k is not None else s.position
        ref = s.best_lap or s.last_lap
        my_prog = s.laps_done + s.lap_frac

        def gap(r) -> float | None:
            """Écart en secondes (> 0 : devant toi), avec la progression dans la course et ton temps au tour."""
            if not ref:
                return None
            d = r["laps"] - my_prog
            return d * ref if abs(d) < 1 else None

        def other(r) -> dict:
            return {"name": r["name"], "car": r["car"], "laps": int(r["laps"]), "place": r["p"],
                    "last_lap": r["last"], "sectors": None, "in_pits": r["pits"]}

        if me_k is not None:
            for k, r in enumerate(same):
                if r["me"]:
                    continue
                o = other(r)
                o["cpos"] = k + 1
                g = gap(r)
                o["gap"] = g
                o["laps_diff"] = int(r["laps"] - my_prog) if abs(r["laps"] - my_prog) >= 1 else 0
                o["best"] = r["best"]
                o["id"] = r["id"]
                s.rivals.append(o)
            if me_k > 0:
                a = same[me_k - 1]
                s.ahead = dict(other(a), cpos=me_k)
                a["rel"] = "ahead"
                g = gap(a)
                s.gap_class_ahead = g if g and g > 0 else None
            if me_k + 1 < len(same):
                b = same[me_k + 1]
                s.behind = dict(other(b), cpos=me_k + 2)
                b["rel"] = "behind"
                g = gap(b)
                s.gap_class_behind = -g if g and g < 0 else None

        # écarts avec la voiture juste devant / derrière sur la piste (toutes catégories)
        if ref and L and not s.in_pits:
            ahead, behind = [], []
            for r in rows:
                if r["me"] or r["pits"]:
                    continue
                d = (r["f"] - s.lap_frac) % 1
                (ahead if d < 0.5 else behind).append(d * ref if d < 0.5 else (1 - d) * ref)
            s.gap_ahead = min(ahead) if ahead else None
            s.gap_behind = min(behind) if behind else None
        return s
