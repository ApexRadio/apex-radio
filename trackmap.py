"""
Carte du circuit.

Le tracé est appris automatiquement : chaque voiture en piste donne sa position
et sa progression dans le tour ; on range ces points dans 400 cases (une par
0,25 % du tour) et on en fait la moyenne. Dès que le tour est couvert, la carte
est sauvegardée dans maps/ et réutilisée les fois suivantes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from telemetry import Snapshot

HERE = Path(__file__).parent
from paths import DATA, LOCAL  # noqa: E402
MAPS = DATA / "maps"
BINS = 400
SAMPLES = 6          # points moyennés par case avant de la figer


def _fname(track: str) -> Path:
    return MAPS / (re.sub(r"[^A-Za-z0-9_-]+", "_", track).strip("_") + ".json")


class TrackMap:
    def __init__(self) -> None:
        self.track = None
        self.sum = []
        self.count = []
        self.sector = []
        self.saved = False
        self.version = 0

    def _load(self, track: str) -> None:
        self.track = track
        self.sum = [[0.0, 0.0] for _ in range(BINS)]
        self.count = [0] * BINS
        self.sector = [None] * BINS
        self.saved = False
        self.version += 1
        try:
            d = json.loads(_fname(track).read_text(encoding="utf-8"))
            for i, (x, z, sec) in enumerate(d["points"]):
                self.sum[i] = [x * SAMPLES, z * SAMPLES]
                self.count[i] = SAMPLES
                self.sector[i] = sec
            self.saved = True
        except Exception:
            pass

    def coverage(self) -> float:
        return sum(1 for c in self.count if c) / BINS

    def update(self, s: Snapshot) -> None:
        if not s.on_track or not s.track:
            return
        if s.track != self.track:
            self._load(s.track)
        if self.saved:
            return
        changed = False
        for c in s.cars:
            if c["pits"] or not (0 <= c["f"] < 1):
                continue
            i = min(BINS - 1, int(c["f"] * BINS))
            if self.count[i] >= SAMPLES:
                continue
            self.sum[i][0] += c["x"]
            self.sum[i][1] += c["z"]
            self.count[i] += 1
            self.sector[i] = c["s"]
            changed = True
        if changed:
            self.version += 1
        if self.coverage() >= 0.97:
            self._fill_gaps()
            MAPS.mkdir(parents=True, exist_ok=True)
            _fname(self.track).write_text(json.dumps({"track": self.track, "points": self.points()}), encoding="utf-8")
            self.saved = True
            self.version += 1
            print(f"  Carte enregistrée : {self.track}")

    def _fill_gaps(self) -> None:
        """Bouche les quelques cases vides en interpolant entre voisines."""
        filled = [i for i in range(BINS) if self.count[i]]
        for i in range(BINS):
            if self.count[i]:
                continue
            prev = max((j for j in filled if j < i), default=filled[-1])
            nxt = min((j for j in filled if j > i), default=filled[0])
            a = self.sum[prev][0] / self.count[prev], self.sum[prev][1] / self.count[prev]
            b = self.sum[nxt][0] / self.count[nxt], self.sum[nxt][1] / self.count[nxt]
            self.sum[i] = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
            self.count[i] = 1
            self.sector[i] = self.sector[prev]

    def points(self) -> list:
        out = []
        for i in range(BINS):
            if self.count[i]:
                k = self.count[i]
                out.append([round(self.sum[i][0] / k, 1), round(self.sum[i][1] / k, 1), self.sector[i]])
            else:
                out.append(None)
        return out

    def corners(self) -> list[dict]:
        """Virages repérés sur le tracé (là où il tourne avec un rayon < 220 m)."""
        if not self.saved:
            return []
        if getattr(self, "_corners_v", None) == self.version:
            return self._corners
        import math
        pts = [p for p in self.points()]
        n = len(pts)
        head, step = [], []
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            head.append(math.atan2(b[1] - a[1], b[0] - a[0]))
            step.append(math.hypot(b[0] - a[0], b[1] - a[1]) or 0.1)
        curv = []
        for i in range(n):
            # courbure lissée sur +-3 cases
            tot_h, tot_s = 0.0, 0.0
            for k in range(-3, 3):
                h1, h2 = head[(i + k) % n], head[(i + k + 1) % n]
                tot_h += (h2 - h1 + math.pi) % (2 * math.pi) - math.pi
                tot_s += step[(i + k) % n]
            curv.append(abs(tot_h) / tot_s)
        hot = [c > 1 / 220 for c in curv]
        groups, cur = [], []
        for i in range(n):
            if hot[i]:
                cur.append(i)
            elif cur:
                groups.append(cur); cur = []
        if cur:
            if groups and groups[0][0] == 0:
                groups[0] = cur + groups[0]
            else:
                groups.append(cur)
        # fusionner les virages très proches (chicanes = 1 virage chacun mais trous de 1-2 cases)
        merged = []
        for g in groups:
            if merged and (g[0] - merged[-1][-1]) % n <= 2:
                merged[-1] += g
            else:
                merged.append(g)
        out = []
        for g in merged:
            if len(g) < 3:
                continue
            mid = g[len(g) // 2]
            p = pts[mid]
            out.append({"id": len(out) + 1, "start": g[0] / n, "end": (g[-1] + 1) / n, "mid": mid / n,
                        "x": p[0], "z": p[1]})
        self._corners, self._corners_v = out, self.version
        return out

    def dist_to_line(self, x: float, z: float, f: float) -> float | None:
        """Distance (m) entre un point et la trajectoire moyenne apprise, autour de la position f dans le tour."""
        if not self.saved:
            return None
        import math
        i0 = int(f * BINS)
        best = None
        for k in range(-6, 7):
            i = (i0 + k) % BINS
            if not self.count[i]:
                continue
            px, pz = self.sum[i][0] / self.count[i], self.sum[i][1] / self.count[i]
            d = math.hypot(px - x, pz - z)
            best = d if best is None or d < best else best
        return best

    def info(self) -> dict:
        return {"track": self.track, "version": self.version, "ready": self.saved,
                "coverage": round(self.coverage() * 100)}
