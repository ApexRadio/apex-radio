"""
Tour de référence : ton meilleur tour propre, virage par virage (étape 1 des références).

Pour chaque voiture et chaque circuit, Apex garde ton meilleur tour valide : où tu commences à freiner,
ta vitesse la plus basse dans le virage et où tu remets les gaz. En roulant, elle compare chaque virage
à cette référence et te dit à la radio quand tu t'en éloignes nettement (« tu freines trop tôt, retarde ton point de freinage »).
Tout reste sur ton PC (Documents\\Apex Radio\\references).
"""

from __future__ import annotations

import json
import random
import re
import threading
import time

from i18n import L
from paths import DATA

REFS = DATA / "references"
LAPS = DATA / "laps"          # courbes des tours (meilleur + derniers) pour la page « Comparer mes tours »
NBIN = 500                    # points par tour (tous les 0,2 % de tour : ~10 m sur un circuit de 5 km)
RECENT = 10                   # derniers tours propres gardés


def _curve(trace) -> dict | None:
    """Vitesse (km/h), frein et gaz (%) moyennés sur NBIN cases le long du tour (trous bouchés)."""
    acc = [[0.0, 0.0, 0.0, 0] for _ in range(NBIN)]
    for x in trace:
        i = min(NBIN - 1, max(0, int(x[0] * NBIN)))
        a = acc[i]
        a[0] += x[1] * 3.6; a[1] += (x[2] or 0) * 100; a[2] += (x[3] or 0) * 100; a[3] += 1
    have = [i for i in range(NBIN) if acc[i][3]]
    if len(have) < NBIN * 0.6:
        return None
    out = {"v": [None] * NBIN, "b": [None] * NBIN, "t": [None] * NBIN}
    for i in have:
        n = acc[i][3]
        out["v"][i] = round(acc[i][0] / n, 1); out["b"][i] = round(acc[i][1] / n); out["t"][i] = round(acc[i][2] / n)
    for k in out:                       # cases vides : on recopie la dernière valeur connue
        arr, last = out[k], None
        for i in list(range(NBIN)) * 2:
            if arr[i] is None:
                if last is not None:
                    arr[i] = last
            else:
                last = arr[i]
    return out

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

    def _keep_lap(self, trace, lap: float, L_m: float) -> None:
        """Garde la courbe de ce tour (et du meilleur) pour la page « Comparer mes tours »."""
        cur = _curve(trace)
        if not cur:
            return
        try:
            f = LAPS / self._file(self.key).name
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                game, track, car, cond = (self.key.split(" | ") + ["", "", "", ""])[:4]
                d = {"key": self.key, "game": game, "track": track, "car": car, "best": None, "recent": [],
                     "wet": cond == "pluie"}
            item = {"lap": round(lap, 3), "date": time.strftime("%Y-%m-%d %H:%M"), "L": round(L_m, 1), **cur}
            d["recent"] = ([item] + d.get("recent", []))[:RECENT]
            if not d.get("best") or lap < d["best"]["lap"] - 0.005:
                d["best"] = item
            LAPS.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
        except Exception as e:
            print(f"  Tours : écriture impossible ({e.__class__.__name__})")

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
        full = [(_rel(x[0], s),) + tuple(x[1:]) + (None, None, 0)[len(x) - 4:] for x in trace]
        full = [p for p in full if -APPROACH <= p[0] <= ln + EXIT]
        pts = [p[:4] for p in full]
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
        out = {"s": round(s, 4), "b": m(brake), "v": round(vmin * 3.6, 1), "t": m(thr)}
        out.update(self._line(full, rv, ln))
        return out

    @staticmethod
    def _line(full, rv, ln) -> dict:
        """Trajectoire au point de corde (vitesse mini) et en sortie : distance au bord de piste le plus proche
        (mPathLateral / mTrackEdge, en mètres, négatif = roues dehors) et vibreurs. Sert aux conseils de ligne,
        dits en mots de pilote (« tu ne vas pas chercher la corde »), jamais en mètres."""
        def room(p):
            pl, edge = p[4], p[5]
            if pl is None or edge is None or abs(edge) < 2:
                return None
            return abs(edge) - abs(pl)          # place jusqu'au bord, côté où se trouve la voiture
        apex = [p for p in full if abs(p[0] - rv) <= 0.004]
        exitp = [p for p in full if ln <= p[0] <= ln + EXIT]
        ra = [room(p) for p in apex if room(p) is not None]
        rx = [room(p) for p in exitp if room(p) is not None]
        if not ra or not rx:
            return {}
        return {"ae": round(min(ra), 2), "ac": int(any(p[6] >= 2 for p in apex)),
                "xe": round(min(rx), 2), "xc": int(any(p[6] >= 2 for p in exitp)),
                "as": 1 if (apex[len(apex) // 2][4] or 0) >= 0 else -1}

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
            import conditions
            # au mouillé : tour de référence et conseils à part (on ne compare pas un virage sous la pluie au sec)
            key = f"{getattr(s, 'game', 'lmu')} | {s.track} | {s.car or s.car_class}" + conditions.tag(conditions.wet(s))
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
            self.trace.append((m["f"], m["speed"], m.get("brk") or 0.0, m.get("thr") or 0.0,
                               m.get("pl"), m.get("edge"), m.get("curb") or 0))
            # bataille / trafic : une voiture à moins de ~150 m devant ou ~100 m derrière. On le retient quelques
            # secondes pour ne pas comparer un virage pris en défense, en attaque ou côte à côte.
            L_m, f = s.track_len, m["f"]
            if any(not o.get("me") and not o.get("pits") and o.get("spd", 0) > 5 and
                   (((o.get("f", 0) - f) % 1) * L_m < 150 or ((f - o.get("f", 0)) % 1) * L_m < 100)
                   for o in (s.cars or [])):
                self.close_t = time.monotonic()
            calm = not s.yellow and s.game_phase != 6 and not (s.session == "course" and s.laps_done < 2)
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
            if 20 < lap < 1200:
                self._keep_lap(trace, lap, L_m)
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
            # une voiture proche pendant ce virage (ou dans les 10 s avant) : on ne compare pas, le trafic fausse tout
            if time.monotonic() - getattr(self, "close_t", -1e9) < 10:
                continue
            ref = self.ref["corners"].get(cid)
            if not ref or abs(_rel(ref["s"], c["start"])) > 0.01:    # carte du circuit changée : on ne compare pas
                continue
            cur = self._corner(self.trace, c, L_m)
            if not cur:
                continue
            d = {"early": (ref["b"] - cur["b"]) if ref["b"] is not None and cur["b"] is not None else 0.0,
                 "dv": cur["v"] - ref["v"],
                 "late": (cur["t"] - ref["t"]) if ref["t"] is not None and cur["t"] is not None else 0.0,
                 "line": self._line_diff(ref, cur)}
            if d["dv"] < -30 or abs(d["early"]) > 80 or d["late"] > 80:   # incident, voiture devant, ralentissement
                continue
            self.last_cmp[cid] = d
            msg = self._advice(cid, d)
            import behavior
            if s.session == "course" and not behavior.COACH_RACE:
                continue   # réglage : pas de conseils virage en course (toujours dispo si tu demandes)
            now = time.monotonic()
            if not msg or now - self.said_at < GAP.get(s.session, GAP_DEFAULT):
                continue
            if self.lap - self.said_corner.get(cid, -99) < 3:
                continue
            self.said_at, self.said_corner[cid] = now, self.lap
            say(None, msg)

    @staticmethod
    def _line_diff(ref: dict, cur: dict) -> str | None:
        """Ce qui change dans la trajectoire par rapport au meilleur tour : "corde", "vibreur", "large", "largeur"."""
        if "ae" not in ref or "ae" not in cur:
            return None                         # référence enregistrée avant les conseils de ligne
        if cur["xe"] < -0.8 and ref["xe"] > -0.3:
            return "large"                      # roues dehors en sortie, pas à la référence
        if ref["as"] == cur["as"] and cur["ae"] - ref["ae"] > 1.2 and ref["ae"] < 1.0:
            return "vibreur" if ref["ac"] and not cur["ac"] else "corde"
        if ref["xe"] < 0.8 and cur["xe"] - ref["xe"] > 1.5:
            return "largeur"                    # n'utilise pas toute la largeur en sortie
        return None

    @staticmethod
    def _advice(cid: str, d: dict) -> str | None:
        e, dv, late = round(d["early"]), round(d["dv"]), round(d["late"])
        line = d.get("line")
        if line == "large":
            return L(f"Virage {cid} : tu sors trop large, tu mets les roues dehors en sortie. Patiente un peu avant de remettre les gaz.",
                     f"Turn {cid}: you're running wide on exit, wheels off. Wait a touch before getting on the power.")
        if line and (dv <= -2 or late >= 10):
            if line == "vibreur":
                return L(f"Virage {cid} : va chercher le vibreur à la corde, comme à ton meilleur tour.",
                         f"Turn {cid}: use the apex kerb, like on your best lap.")
            if line == "corde":
                return L(f"Virage {cid} : tu es loin de la corde, resserre ta trajectoire.",
                         f"Turn {cid}: you're missing the apex, tighten your line.")
            if line == "largeur":
                return L(f"Virage {cid} : utilise toute la largeur en sortie, tu pourras remettre les gaz plus tôt.",
                         f"Turn {cid}: use all the track on exit, you'll get on the power earlier.")
        # en mots d'ingénieur, jamais en mètres ni en km/h (« tu freines 26 m plus tôt » ne sonne pas pro)
        if e >= 15 and dv < 3:
            big = e >= 30
            return random.choice([
                L(f"Virage {cid} : tu freines {'beaucoup ' if big else ''}trop tôt, il y a du temps à prendre. Retarde ton point de freinage.",
                  f"Turn {cid}: you're braking {'way ' if big else ''}too early, there's time there. Push your braking point later."),
                L(f"Virage {cid} : tu peux freiner plus tard, tu laisses du temps à l'entrée.",
                  f"Turn {cid}: you can brake later, you're leaving time on entry."),
                L(f"Virage {cid} : freinage {'nettement ' if big else ''}en avance sur ta référence, attaque plus tard.",
                  f"Turn {cid}: braking {'well ' if big else ''}ahead of your reference, go in deeper.")])
        if e <= -15 and dv <= -4:
            return random.choice([
                L(f"Virage {cid} : tu freines trop tard et tu perds de la vitesse au point de corde. Freine un peu plus tôt, tu sortiras plus vite.",
                  f"Turn {cid}: you're braking too late and losing apex speed. Brake a touch earlier, you'll exit faster."),
                L(f"Virage {cid} : tu en mets trop à l'entrée, la vitesse de passage chute. Reviens à ton point de freinage habituel.",
                  f"Turn {cid}: you're overdoing the entry, the minimum speed drops. Go back to your usual braking point.")])
        if dv <= -6:
            big = dv <= -12
            return random.choice([
                L(f"Virage {cid} : tu passes {'nettement ' if big else ''}moins vite qu'à ton meilleur tour. Porte plus de vitesse au point de corde.",
                  f"Turn {cid}: you're {'much ' if big else ''}slower than your best lap through there. Carry more speed to the apex."),
                L(f"Virage {cid} : vitesse de passage en dessous de ta référence. Relâche le frein plus tôt et laisse rouler la voiture.",
                  f"Turn {cid}: minimum speed below your reference. Release the brake earlier and let the car roll."),
                L(f"Virage {cid} : tu es trop lent au milieu du virage, fais-lui confiance, la voiture peut en prendre plus.",
                  f"Turn {cid}: too slow mid-corner, trust it, the car can take more.")])
        if late >= 20:
            return random.choice([
                L(f"Virage {cid} : tu remets les gaz trop tard. Ouvre plus tôt pour mieux sortir.",
                  f"Turn {cid}: you're late on the throttle. Get on it earlier for a better exit."),
                L(f"Virage {cid} : sortie timide, tu peux accélérer plus tôt qu'en ce moment.",
                  f"Turn {cid}: hesitant exit, you can get on the power sooner.")])
        return None

    # ------------------------------------------------------------- questions
    def report(self) -> str:
        with self.lock:
            if not self.ref:
                return L("Je n'ai pas encore de tour de référence pour cette voiture ici : fais un tour propre et valide.",
                         "I don't have a reference lap for this car here yet: do a clean, valid lap.")
            score = lambda d: max(d["early"] / 10, -d["dv"] / 3, d["late"] / 15, 1.5 if d.get("line") == "large" else 0)
            worst = sorted(((score(d), cid, d) for cid, d in self.last_cmp.items() if score(d) >= 1), reverse=True)[:3]
            if not worst:
                return L("Par rapport à ton meilleur tour, rien de net à signaler, tu es dans tes marques.",
                         "Compared to your best lap, nothing clear to report, you're on your marks.")
            parts = []
            for _, cid, d in worst:
                ln = {"corde": L("loin de la corde", "missing the apex"), "vibreur": L("tu ne prends pas le vibreur à la corde", "not using the apex kerb"),
                      "large": L("tu sors trop large", "running wide on exit"), "largeur": L("tu n'utilises pas toute la largeur en sortie", "not using all the track on exit")}.get(d.get("line"))
                if ln:
                    parts.append(L(f"virage {cid}, {ln}", f"turn {cid}, {ln}"))
                elif d["early"] >= 10:
                    parts.append(L(f"virage {cid}, tu freines trop tôt", f"turn {cid}, braking too early"))
                elif d["dv"] <= -3:
                    parts.append(L(f"virage {cid}, pas assez de vitesse au point de corde", f"turn {cid}, not enough apex speed"))
                else:
                    parts.append(L(f"virage {cid}, tu remets les gaz trop tard", f"turn {cid}, late on the throttle"))
            return L("Par rapport à ton meilleur tour : ", "Compared to your best lap: ") + " ; ".join(parts) + "."
