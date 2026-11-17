# -*- coding: utf-8 -*-
"""
Apex Radio - outil de test iRacing / iRacing test tool.

Lit les données qu'iRacing partage officiellement (iRacing SDK, mémoire partagée
"Local\\IRSDKMemMapFileName") et les enregistre dans :
    Documents\\Apex Radio\\iracing_test\\
Le fichier a envoyer est : Documents\\Apex Radio\\iracing_test\\RESULTATS_iRacing.zip
(il est mis a jour automatiquement pendant que tu roules).

Lecture seule : l'outil ne modifie rien dans le jeu.
Read-only: the tool changes nothing in the game.
"""
import ctypes as C
import ctypes.wintypes as W
import json
import os
import time
import zipfile
from datetime import datetime

MAP_NAME = "Local\\IRSDKMemMapFileName"
FILE_MAP_READ = 4

# types iRacing : 0 char, 1 bool, 2 int, 3 bitfield, 4 float, 5 double
TYPES = {0: (C.c_char, 1), 1: (C.c_bool, 1), 2: (C.c_int32, 4), 3: (C.c_uint32, 4), 4: (C.c_float, 4), 5: (C.c_double, 8)}


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


k32 = C.WinDLL("kernel32", use_last_error=True)
k32.OpenFileMappingW.restype = W.HANDLE
k32.OpenFileMappingW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
k32.MapViewOfFile.restype = C.c_void_p
k32.MapViewOfFile.argtypes = [W.HANDLE, W.DWORD, W.DWORD, W.DWORD, C.c_size_t]


class IR:
    def __init__(self):
        self.ptr = None
        self.vars = None

    def open(self):
        if self.ptr:
            return True
        h = k32.OpenFileMappingW(FILE_MAP_READ, False, MAP_NAME)
        if not h:
            return False
        p = k32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, 0)
        if not p:
            return False
        self.ptr = p
        return True

    def header(self):
        return Header.from_buffer_copy(C.string_at(self.ptr, C.sizeof(Header)))

    def var_headers(self, h):
        raw = C.string_at(self.ptr + h.varHeaderOffset, h.numVars * C.sizeof(VarHeader))
        out = []
        for i in range(h.numVars):
            v = VarHeader.from_buffer_copy(raw[i * C.sizeof(VarHeader):(i + 1) * C.sizeof(VarHeader)])
            out.append({"name": v.name.decode("latin-1", "replace"), "type": v.type, "offset": v.offset,
                        "count": v.count, "unit": v.unit.decode("latin-1", "replace"),
                        "desc": v.desc.decode("latin-1", "replace")})
        return out

    def session_yaml(self, h):
        return C.string_at(self.ptr + h.sessionInfoOffset, h.sessionInfoLen).split(b"\0", 1)[0].decode("latin-1", "replace")

    def values(self, h):
        """Toutes les variables du dernier tampon complet."""
        if self.vars is None or len(self.vars) != h.numVars:
            self.vars = self.var_headers(h)
        for _ in range(3):
            i = max(range(h.numBuf), key=lambda k: h.varBuf[k].tickCount)
            b = h.varBuf[i]
            raw = C.string_at(self.ptr + b.bufOffset, h.bufLen)
            h2 = self.header()
            if h2.varBuf[i].tickCount == b.tickCount:   # le tampon n'a pas été réécrit pendant la lecture
                break
            h = h2
        out = {"_tick": b.tickCount}
        for v in self.vars:
            ct, sz = TYPES.get(v["type"], (C.c_float, 4))
            arr = (ct * v["count"]).from_buffer_copy(raw[v["offset"]:v["offset"] + sz * v["count"]])
            vals = list(arr)
            if v["type"] == 0:
                vals = [x.decode("latin-1", "replace") if isinstance(x, bytes) else x for x in vals]
            if v["type"] in (4, 5):
                vals = [round(float(x), 4) for x in vals]
            out[v["name"]] = vals[0] if v["count"] == 1 else vals
        return out


def g(d, k, i=None, nd=1):
    v = d.get(k)
    if v is None:
        return None
    if i is not None and isinstance(v, list):
        v = v[i] if i < len(v) else None
    if isinstance(v, float):
        return round(v, nd)
    return v


def lisible(d):
    me = d.get("PlayerCarIdx", 0) or 0
    return (f"[{datetime.now():%H:%M:%S}] piste {g(d, 'IsOnTrack')} | séance {g(d, 'SessionNum')} état {g(d, 'SessionState')} "
            f"reste {g(d, 'SessionTimeRemain', nd=0)} s, tours restants {g(d, 'SessionLapsRemainEx')} | "
            f"{g(d, 'Speed')} m/s R{g(d, 'Gear')} | essence {g(d, 'FuelLevel', nd=2)} L ({g(d, 'FuelLevelPct', nd=3)})\n"
            f"   P{g(d, 'PlayerCarPosition')} (classe P{g(d, 'PlayerCarClassPosition')}) tour {g(d, 'Lap')} "
            f"({g(d, 'LapDistPct', nd=3)}) | dernier {g(d, 'LapLastLapTime', nd=3)} meilleur {g(d, 'LapBestLapTime', nd=3)} | "
            f"stand {g(d, 'OnPitRoad')} limiteur(EngineWarnings) {g(d, 'EngineWarnings')} | drapeaux {g(d, 'SessionFlags')}\n"
            f"   voitures : pos {str(g(d, 'CarIdxPosition'))[:80]}… | écart estimé moi {g(d, 'CarIdxEstTime', me, 2)} s\n")


def main():
    base = os.path.join(os.path.expanduser("~"), "Documents", "Apex Radio", "iracing_test")
    snaps = os.path.join(base, "mesures")
    os.makedirs(snaps, exist_ok=True)
    log = open(os.path.join(base, "journal_lisible.txt"), "a", encoding="utf-8")

    def say(m):
        print(m, end="" if m.endswith("\n") else "\n", flush=True)
        log.write(m if m.endswith("\n") else m + "\n")
        log.flush()

    def make_zip():
        z = os.path.join(base, "RESULTATS_iRacing.zip")
        tmp = z + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(base):
                for f in files:
                    if f.startswith("RESULTATS_iRacing.zip"):
                        continue
                    p = os.path.join(root, f)
                    zf.write(p, os.path.relpath(p, base))
        os.replace(tmp, z)

    say(f"=== Test iRacing démarré / started {datetime.now():%d/%m/%Y %H:%M} ===")
    say("En attente d'iRacing... Laisse cette fenêtre ouverte pendant que tu roules.")
    say("Waiting for iRacing... Keep this window open while you drive.")
    ir = IR()
    connected = False
    last_snap = last_zip = 0.0
    last_sess = -1
    n = 0
    while True:
        try:
            if not ir.open():
                time.sleep(2)
                continue
            h = ir.header()
            if not (h.status & 1):          # irsdk_stConnected
                if connected:
                    say("iRacing n'est plus en séance (menu ou jeu fermé).")
                    connected = False
                    make_zip()
                time.sleep(2)
                continue
            if not connected:
                connected = True
                vh = ir.var_headers(h)
                say(f"Connecté à iRacing ! SDK v{h.ver}, {h.numVars} variables, {h.tickRate} lectures/s.")
                json.dump(vh, open(os.path.join(base, "variables.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            if h.sessionInfoUpdate != last_sess:
                last_sess = h.sessionInfoUpdate
                with open(os.path.join(base, f"session_{datetime.now():%H%M%S}.yaml"), "w", encoding="utf-8") as f:
                    f.write(ir.session_yaml(h))
            d = ir.values(h)
            say(lisible(d))
            now = time.time()
            if now - last_snap >= 10 and n < 500:
                last_snap = now
                n += 1
                d["_heure"] = datetime.now().isoformat(timespec="seconds")
                with open(os.path.join(snaps, f"{datetime.now():%H%M%S}.json"), "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False)
            if now - last_zip >= 60:
                last_zip = now
                make_zip()
            time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception as ex:
            say(f"Erreur : {ex!r}")
            time.sleep(3)
    make_zip()
    say("=== Test terminé / finished ===")


if __name__ == "__main__":
    main()
