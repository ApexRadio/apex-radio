"""
Tour de référence : ton meilleur tour propre, virage par virage (étape 1 des références).

Pour chaque voiture et chaque circuit, Apex garde ton meilleur tour valide : où tu commences à freiner,
ta vitesse la plus basse dans le virage et où tu remets les gaz. En roulant, elle compare chaque virage
à cette référence et te dit à la radio quand tu t'en éloignes nettement (« tu freines 20 mètres plus tôt »).
Tout reste sur ton PC (Documents\\Apex Radio\\references).
"""

from __future__ import annotations

import json
import re
import threading
import time

from i18n import L
from paths import DATA

REFS = DATA / "references"

APPROACH = 0.06      # on cherche le freinage jusqu'à 6 % de tour avant le virage
EXIT = 0.04          # et la remise des gaz jusqu'à 4 % après
GAP = {"course": 120.0}   # s entre deux conseils (en course on parle moins)
GAP_DEFAULT = 25.0


def _rel(f: float, start: float) -> float:
    """Distance (en fraction de tour, avec signe) entre la position f et le début du virage."""
    return (f - start + 0.5) % 1 - 0.5


class RefLap:
    def __init__(self, behavior) -> None:
        self.beh = behavior
        self.lock = threading.Lock()
        self.key = None
        self.ref = None              # {"lap": s, "L": m, "corners": {id: {...}}}
        self.lap = None
        self.trace = []              # tour en cours : (f, vitesse m/s, frein, gaz)
        self.clean = False
        self.pending = None          # tour terminé, en attente de son chrono officiel
        self.done = set()            # virages déjà comparés sur ce tour
        self.last_cmp = {}           # virage -> écarts du dernier tour (pour « où je perds du temps »)
        self.said_at = -999.0
        self.said_corner = {}        # virage -> tour du dernier conseil

    # ------------------------------------------------------------- fichiers
    @staticmethod
    def _file(key: str):
        return REFS / (re.sub(r"[^A-Za-z0-9_-]+", "_", key).strip("_") + ".json")

    def _load(self, key: str) -> None:
        self.key, self.ref, self.last_cmp, self.said_corner = key, None, {}, {}
        try:
            self.ref = json.loads(self._file(key).read_text(encoding="utf-8"))
        except Exception:
            pass

    def _save(self, ref: dict) -> None:
        try:
            REFS.mkdir(parents=True, exist_ok=True)
            self._file(self.key).write_text(json.dumps(ref, indent=1, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"  Référence : écriture impossible ({e.__class__.__name__})")

    # ------------------------------------------------------------- mesures
    def _corner(self, trace, c, L_m):
        """Freinage, vitesse mini et remise des gaz pour un virage, à partir des mesures du tour."""
        s = c["start"]
        ln = (c["end"] - s) % 1
        pts = [(_rel(f, s), v, b, t) for f, v, b, t in trace]
        pts = [p for p in pts if -APPROACH <= p[0] <= ln + EXIT]
        if len(pts) < 10:
            return None
        brake, prev = None, 1.0
        for r, v, b, t in pts:
            if r > ln * 0.6:
                break
            if b > 0.2 and prev < 0.1:
                brake = r
                break
            prev = b
        inside = [p for p in pts if -0.01 <= p[0] <= ln]
        if not inside:
            return None
        k = min(range(len(inside)), key=lambda i: inside[i][1])
        rv, vmin = inside[k][0], inside[k][1]
        thr = next((r for r, v, b, t in pts if r > rv and t > 0.8), None)
        m = lambda r: None if r is None else round(r * L_m, 1)
        return {"s": round(s, 4), "b": m(brake), "v": round(vmin * 3.6, 1), "t": m(thr)}

    def _all_corners(self, trace, L_m):
        out = {}
        for c in self.beh.map.corners():
            r = self._corner(trace, c, L_m)
            if r:
                out[str(c["id"])] = r
        return out

    # ------------------------------------------------------------- en direct
    def feed(self, m: dict | None, s, say) -> None:
        if not m or not s or not s.track or not s.track_len:
            return
        with self.lock:
            key = f"{getattr(s, 'game', 'lmu')} | {s.track} | {s.car or s.car_class}"
            if key != self.key:
                self._load(key)
                self.lap, self.trace, self.pending = None, [], None
            self._resolve(s)
            if self.lap is None:
                self.lap = m["lap"]
            if m["lap"] != self.lap:
                if m["lap"] > self.lap and self.clean and len(self.trace) > 200 and self.trace[0][0] < 0.03:
                    self.pending = (self.trace, getattr(self, "mid_last", None), time.monotonic(), s.track_len)
                self.lap, self.trace, self.done = m["lap"], [], set()
                self.clean, self.lap_t0 = not m["pits"], time.monotonic()
            # « tour invalide » du jeu : lu 5 fois/s, il traîne un instant après la ligne (c'était l'ancien tour)
            if m["pits"] or (s.lap_invalid and time.monotonic() - getattr(self, "lap_t0", 0) > 1.5):
                self.clean = False
            if m["pits"]:
                return
            if 0.4 < m["f"] < 0.6:
                self.mid_last = s.last_lap      # chrono du tour PRÉCÉDENT : il changera quand ce tour-ci sera fini
            self.trace.append((m["f"], m["speed"], m.get("brk") or 0.0, m.get("thr") or 0.0))
            calm = not s.yellow and s.game_phase != 6 and not (s.session == "course" and s.laps_done < 2) \
                and not getattr(s, "oval", False)          # ovale : l'aspiration fausse tout, on ne compare pas
            import behavior
            if self.ref and self.clean and calm and behavior.COACH:
                self._compare(m["f"], s, say)

    def _resolve(self, s) -> None:
        """Le chrono du tour arrive un peu après le passage de la ligne : on attend qu'il change."""
        if not self.pending:
            return
        trace, before, t0, L_m = self.pending
        if s.last_lap and s.last_lap != before:
            self.pending = None
            lap = s.last_lap
            if not self.ref or lap < self.ref.get("lap", 9e9) - 0.005:
                corners = self._all_corners(trace, L_m)
                if len(corners) >= max(1, len(self.beh.map.corners()) // 2):
                    self.ref = {"lap": round(lap, 3), "L": round(L_m, 1), "date": time.strftime("%Y-%m-%d %H:%M"),
                                "corners": corners}
                    self._save(self.ref)
                    print(f"  Référence : nouveau meilleur tour {lap:.3f} s ({self.key})")
        elif time.monotonic() - t0 > 12:
            self.pending = None

    def _compare(self, f: float, s, say) -> None:
        L_m = s.track_len
        for c in self.beh.map.corners():
            cid = str(c["id"])
            if cid in self.done:
                continue
            ln = (c["end"] - c["start"]) % 1
            r = _rel(f, c["start"])
            if not (ln + EXIT + 0.005 < r < ln + EXIT + 0.05):
                continue
            self.done.add(cid)
            # une voiture juste devant (ou qui te colle) dans ce virage : on ne compare pas, le trafic fausse tout
            if any(not o.get("me") and ((o.get("f", 0) - f) % 1 < 0.025 or (f - o.get("f", 0)) % 1 < 0.01)
                   for o in s.cars):
                continue
            ref = self.ref["corners"].get(cid)
            if not ref or abs(_rel(ref["s"], c["start"])) > 0.01:    # carte du circuit changée : on ne compare pas
                continue
            cur = self._corner(self.trace, c, L_m)
            if not cur:
                continue
            d = {"early": (ref["b"] - cur["b"]) if ref["b"] is not None and cur["b"] is not None else 0.0,
                 "dv": cur["v"] - ref["v"],
                 "late": (cur["t"] - ref["t"]) if ref["t"] is not None and cur["t"] is not None else 0.0}
            if d["dv"] < -30 or abs(d["early"]) > 80 or d["late"] > 80:   # incident, voiture devant, ralentissement
                continue
            self.last_cmp[cid] = d
            msg = self._advice(cid, d)
            now = time.monotonic()
            if not msg or now - self.said_at < GAP.get(s.session, GAP_DEFAULT):
                continue
            if self.lap - self.said_corner.get(cid, -99) < 3:
                continue
            self.said_at, self.said_corner[cid] = now, self.lap
            say(None, msg)

    @staticmethod
    def _advice(cid: str, d: dict) -> str | None:
        e, dv, late = round(d["early"]), round(d["dv"]), round(d["late"])
        if e >= 15 and dv < 3:
            return L(f"Virage {cid} : tu freines {e} mètres plus tôt qu'à ton meilleur tour.",
                     f"Turn {cid}: you're braking {e} metres earlier than on your best lap.")
        if e <= -15 and dv <= -4:
            return L(f"Virage {cid} : tu freines {-e} mètres plus tard que ta référence mais tu passes {-dv} kilomètres heure "
                     f"moins vite. Freine un peu plus tôt.",
                     f"Turn {cid}: you're braking {-e} metres later than your reference but you're {-dv} k p h slower. "
                     f"Brake a bit earlier.")
        if dv <= -6:
            return L(f"Virage {cid} : {-dv} kilomètres heure de moins qu'à ton meilleur tour au point le plus lent.",
                     f"Turn {cid}: {-dv} k p h slower than your best lap at the slowest point.")
        if late >= 20:
            return L(f"Virage {cid} : tu remets les gaz {late} mètres plus tard qu'à ton meilleur tour.",
                     f"Turn {cid}: you're back on the throttle {late} metres later than on your best lap.")
        return None

    # ------------------------------------------------------------- questions
    def report(self) -> str:
        with self.lock:
            if not self.ref:
                return L("Je n'ai pas encore de tour de référence pour cette voiture ici : fais un tour propre et valide.",
                         "I don't have a reference lap for this car here yet: do a clean, valid lap.")
            score = lambda d: max(d["early"] / 10, -d["dv"] / 3, d["late"] / 15)
            worst = sorted(((score(d), cid, d) for cid, d in self.last_cmp.items() if score(d) >= 1), reverse=True)[:3]
            if not worst:
                return L("Par rapport à ton meilleur tour, rien de net à signaler, tu es dans tes marques.",
                         "Compared to your best lap, nothing clear to report, you're on your marks.")
            parts = []
            for _, cid, d in worst:
                if d["early"] >= 10:
                    parts.append(L(f"virage {cid}, tu freines {round(d['early'])} mètres plus tôt",
                                   f"turn {cid}, braking {round(d['early'])} metres earlier"))
                elif d["dv"] <= -3:
                    parts.append(L(f"virage {cid}, {round(-d['dv'])} kilomètres heure de moins",
                                   f"turn {cid}, {round(-d['dv'])} k p h slower"))
                else:
                    parts.append(L(f"virage {cid}, tu remets les gaz {round(d['late'])} mètres plus tard",
                                   f"turn {cid}, throttle {round(d['late'])} metres later"))
            return L("Par rapport à ton meilleur tour : ", "Compared to your best lap: ") + " ; ".join(parts) + "."
