"""
Planificateur de relais pour les courses d'endurance en équipe.

Avant la course (page RELAIS du tableau de bord) : les pilotes, la durée de la course et la durée
visée d'un relais. Apex en déduit le plan (combien de relais, qui roule quand).

En course, sur le PC où Apex tourne :
- au départ, il rappelle le plan ;
- il choisit le bon arrêt pour changer de pilote : à chaque arrêt essence prévu, il regarde si le
  relais en cours est plus proche de sa durée visée en s'arrêtant là ou au plein suivant ;
- s'il n'y a pas d'arrêt essence au bon moment (relais plus courts qu'un plein), il annonce la fin
  du relais à l'heure ;
- après chaque changement de pilote, le temps qui reste est réparti entre les relais restants :
  si un relais a duré plus ou moins longtemps (dégâts, neutralisation…), le plan se recalcule tout seul.

Le pilote au volant est reconnu par son nom dans le jeu quand il correspond à un des pilotes entrés.
"""

from __future__ import annotations

import json
import math
import re

from i18n import L
from paths import DATA

CFG = DATA / "relais.json"
TANKS = DATA / "relais_pleins.json"     # durée d'un plein retenue par circuit + voiture (le planning reste jeu fermé)
DEFAULT = {"on": False, "drivers": ["", ""], "race_min": 360, "stint_min": 60, "mode": "pleins", "tanks": 2, "tank_min": 0, "tyres": True,
           "name": "", "date": "", "start": "", "unavail": {}}


def load() -> dict:
    try:
        cfg = {**DEFAULT, **json.loads(CFG.read_text(encoding="utf-8"))}
    except Exception:
        cfg = dict(DEFAULT)
    return clean(cfg)


def clean(cfg: dict) -> dict:
    drivers = [str(d).strip()[:24] for d in (cfg.get("drivers") or []) if str(d).strip()][:8]
    try:
        race = max(10, min(48 * 60, int(float(cfg.get("race_min") or 0))))
    except (TypeError, ValueError):
        race = DEFAULT["race_min"]
    try:
        stint = max(10, min(6 * 60, int(float(cfg.get("stint_min") or 0))))
    except (TypeError, ValueError):
        stint = DEFAULT["stint_min"]
    try:
        tanks = max(1, min(10, int(float(cfg.get("tanks") or 2))))
    except (TypeError, ValueError):
        tanks = 2
    try:
        tank_min = max(0, min(300, int(float(cfg.get("tank_min") or 0))))    # 0 = automatique
    except (TypeError, ValueError):
        tank_min = 0
    mode = "temps" if cfg.get("mode") == "temps" else "pleins"
    start = str(cfg.get("start") or "").strip()
    start = start if re.fullmatch(r"([01]?\d|2[0-3])[:h][0-5]\d", start) else ""
    date = str(cfg.get("date") or "").strip()
    date = date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else ""
    un = cfg.get("unavail") or {}
    un = {str(k)[:24]: str(v)[:120] for k, v in (un.items() if isinstance(un, dict) else []) if str(k).strip() and str(v).strip()}
    return {"on": bool(cfg.get("on")), "drivers": drivers, "race_min": race, "stint_min": stint,
            "mode": mode, "tanks": tanks, "tank_min": tank_min, "tyres": cfg.get("tyres", True) is not False,
            "name": str(cfg.get("name") or "").strip()[:60], "date": date, "start": start.replace("h", ":"), "unavail": un}


def _hm(txt: str) -> int | None:
    """« 21:53 » ou « 21h53 » → minutes depuis minuit."""
    m = re.fullmatch(r"\s*([01]?\d|2[0-3])[:h]([0-5]\d)\s*", txt or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def windows(cfg: dict, driver: str) -> list[tuple[int, int]]:
    """Indisponibilités d'un pilote, en minutes depuis le départ : « 21:50-22:50, 01:00-02:00 »."""
    t0 = _hm(cfg.get("start", ""))
    if t0 is None:
        return []
    out = []
    for part in re.split(r"[,;]", (cfg.get("unavail") or {}).get(driver, "")):
        a, _, b = part.partition("-")
        ma, mb = _hm(a), _hm(b)
        if ma is None or mb is None:
            continue
        ra, rb = (ma - t0) % 1440, (mb - t0) % 1440
        if rb <= ra:
            rb += 1440
        out.append((ra, rb))
    return out


def clock(cfg: dict, minute: float | None) -> str | None:
    """Minutes depuis le départ → heure réelle (« 23:48 ») si l'heure de départ est connue."""
    t0 = _hm(cfg.get("start", ""))
    if t0 is None or minute is None:
        return None
    m = int(round(t0 + minute)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _assign(cfg: dict, stints: list[dict]) -> list[dict]:
    """Répartit les pilotes à tour de rôle en sautant ceux qui ne sont pas disponibles pendant le relais."""
    d = names(cfg)
    busy = {x: windows(cfg, x) for x in d}
    k = 0
    for st in stints:
        pick = None
        for j in range(len(d)):
            cand = d[(k + j) % len(d)]
            if st["start"] is None or not any(a < st["end"] and st["start"] < b for a, b in busy[cand]):
                pick = (k + j) % len(d)
                break
        if pick is None:
            pick = k % len(d)
            st["clash"] = True          # personne de libre : on garde l'ordre, et on le signale
        st["driver"] = d[pick]
        st["clock_start"], st["clock_end"] = clock(cfg, st["start"]), clock(cfg, st["end"])
        k = pick + 1
    return stints


RACES = DATA / "relais_courses.json"   # courses gardées (« 6h de Spa », « 4h de Monza »…) pour les préparer à l'avance


def _races() -> dict:
    try:
        d = json.loads(RACES.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def races() -> list[dict]:
    """Liste des courses gardées, les plus proches d'abord."""
    out = [{"key": k, "name": v.get("name") or k, "date": v.get("date", ""), "start": v.get("start", "")}
           for k, v in _races().items() if isinstance(v, dict)]
    return sorted(out, key=lambda r: (r["date"] or "9999", r["name"].lower()))


def race_store(cfg: dict) -> str:
    cfg = clean(cfg)
    key = (cfg.get("name") or L("Course sans nom", "Untitled race")).strip()
    d = _races()
    d[key] = cfg
    try:
        RACES.parent.mkdir(parents=True, exist_ok=True)
        RACES.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return key


def race_get(key: str) -> dict | None:
    v = _races().get(key)
    return clean(v) if isinstance(v, dict) else None


def race_drop(key: str) -> None:
    d = _races()
    if d.pop(key, None) is not None:
        try:
            RACES.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def save(cfg: dict) -> dict:
    cfg = clean(cfg)
    try:
        CFG.parent.mkdir(parents=True, exist_ok=True)
        CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return cfg


def _tank_key(snap) -> str:
    return f"{getattr(snap, 'track', '') or ''}|{getattr(snap, 'car', '') or ''}"


def tank_remember(snap, minutes: float) -> None:
    """Retient la durée d'un plein mesurée en roulant (par circuit + voiture, et la dernière)."""
    try:
        d = json.loads(TANKS.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    m = round(minutes)
    k = _tank_key(snap)
    if d.get(k) == m and d.get("_last") == m:
        return
    if k != "|":
        d[k] = m
    d["_last"] = m
    try:
        TANKS.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def tank_recall(snap=None) -> int | None:
    """Dernière durée d'un plein connue : pour ce circuit + cette voiture, sinon la dernière mesurée."""
    try:
        d = json.loads(TANKS.read_text(encoding="utf-8"))
    except Exception:
        return None
    v = d.get(_tank_key(snap)) if snap is not None else None
    return v or d.get("_last")


def tank_minutes(cfg: dict, live: float | None = None, snap=None) -> tuple[int | None, str]:
    """Durée d'un plein pour le planning : celle tapée à la main, sinon mesurée en roulant, sinon la dernière retenue."""
    if cfg.get("tank_min"):
        return cfg["tank_min"], "manuel"
    if live:
        return round(live), "live"
    r = tank_recall(snap)
    return (r, "memo") if r else (None, "")


def names(cfg: dict) -> list[str]:
    return cfg["drivers"] or [L("Pilote 1", "Driver 1"), L("Pilote 2", "Driver 2")]


def stint_min(cfg: dict, fuel_min: float | None = None) -> float | None:
    """Durée d'un relais en minutes : la durée visée, ou N pleins (si on connaît la durée d'un plein)."""
    if cfg["mode"] == "pleins":
        return cfg["tanks"] * fuel_min if fuel_min else None
    return cfg["stint_min"]


def count(cfg: dict, fuel_min: float | None = None) -> int:
    """Nombre de relais : la durée visée est un maximum souple (10 % de marge avant d'ajouter un relais)."""
    sm = stint_min(cfg, fuel_min)
    if not sm:
        return 0           # en pleins, sans durée de plein connue : on ne sait pas encore
    return max(1, math.ceil(cfg["race_min"] / (sm * 1.1)))


def plan(cfg: dict, fuel_min: float | None = None) -> list[dict]:
    return _assign(cfg, _plan(cfg, fuel_min))


def _plan(cfg: dict, fuel_min: float | None = None) -> list[dict]:
    """Plan théorique : relais de même durée, pilotes à tour de rôle."""
    n, d = count(cfg, fuel_min), names(cfg)
    if not n:
        return [{"n": i + 1, "driver": d[i % len(d)], "start": None, "end": None} for i in range(max(len(d), 2))]
    if cfg["mode"] == "pleins":
        # relais de N pleins chacun, le dernier finit la course
        sm, race = stint_min(cfg, fuel_min), cfg["race_min"]
        n = max(1, math.ceil(race / sm - 0.05))
        return [{"n": i + 1, "driver": d[i % len(d)], "start": round(i * sm), "end": round(min(race, (i + 1) * sm))}
                for i in range(n)]
    dur = cfg["race_min"] / n
    return [{"n": i + 1, "driver": d[i % len(d)], "start": round(i * dur), "end": round((i + 1) * dur)} for i in range(n)]


def _min(sec: float) -> str:
    m = max(1, round(sec / 60))
    if m >= 60:
        h, r = divmod(m, 60)
        tail_fr = (f" {r}" if r >= 10 else f" et {r} minute{'s' if r > 1 else ''}") if r else ""
        tail_en = f" and {r} minute{'s' if r > 1 else ''}" if r else ""
        return L(f"{h} heure{'s' if h > 1 else ''}{tail_fr}", f"{h} hour{'s' if h > 1 else ''}{tail_en}")
    return L(f"{m} minute{'s' if m > 1 else ''}", f"{m} minute{'s' if m > 1 else ''}")


def _same(a: str, b: str) -> bool:
    """« Laurent » correspond à « L. Jeorgelin » ? On compare les mots (prénom ou nom)."""
    wa = {w.strip(".").lower() for w in a.split() if len(w.strip(".")) > 1}
    wb = {w.strip(".").lower() for w in b.split() if len(w.strip(".")) > 1}
    return bool(wa & wb)


class Relay:
    LAST = None   # lu par les questions (« qui roule après ? »)

    def __init__(self) -> None:
        self.cfg = load()
        self.key = None
        Relay.LAST = self
        self._reset()

    def reload(self, cfg: dict | None = None) -> dict:
        self.cfg = save(cfg) if cfg is not None else load()
        return self.cfg

    def _reset(self) -> None:
        self.n = count(self.cfg)
        self.done = 0               # relais terminés
        self.cur = 0                # index du pilote au volant dans la liste
        self.stint_start = None     # temps de séance au début du relais en cours (s)
        self.last_driver = None
        self.last_stops = None
        self.pending = False        # le prochain arrêt est un changement de pilote
        self.said = set()
        self.target = None          # durée visée du relais en cours (s)
        self.driven = 0.0
        self.remaining = None
        self.stops0 = 0

    # ------------------------------------------------------------------ en course
    def _tanks(self) -> str:
        k = self.cfg["tanks"]
        return L(f"{k} plein{'s' if k > 1 else ''}", f"{k} tank{'s' if k > 1 else ''}")

    def _tyres(self) -> str:
        return L(", avec 4 pneus neufs", ", with four new tyres") if self.cfg["tyres"] else ""

    def update(self, s, p, say) -> None:
        try:   # durée d'un plein, pour placer les relais dans le temps (indisponibilités)
            if p is not None and p.fuel_per_lap and p.avg_lap and getattr(s, "fuel_capacity", 0):
                self._fullmin = round(s.fuel_capacity / p.fuel_per_lap * p.avg_lap / 60)
        except Exception:
            pass
        eng = getattr(self, "eng", None)
        if eng is not None:
            eng.relay_tyres = False
        if not self.cfg["on"] or s.session != "course" or not s.on_track or s.done:
            return
        key = (s.track, s.session_code)
        if key != self.key:
            self.key = key
            self._reset()
        d = names(self.cfg)
        pleins = self.cfg["mode"] == "pleins"
        if self.stint_start is None:
            if s.game_phase not in (5,) and s.laps_done == 0:
                return            # on attend le feu vert
            self.stint_start, self.last_stops, self.last_driver = s.elapsed, s.pit_stops, s.driver
            self.stops0 = s.pit_stops
            self._match(s.driver)
            order = ", ".join(d[(self.cur + i) % len(d)] for i in range(len(d)))
            if pleins:
                say(None, L(f"Plan de relais : {self._tanks()} chacun, changement de pilote à l'arrêt{self._tyres()}. Ordre : {order}.",
                            f"Stint plan: {self._tanks()} each, driver change at the stop{self._tyres()}. Order: {order}."))
                return
            # durée réelle de la course donnée par le jeu : elle prime sur celle entrée dans la page
            if s.time_left is not None and s.time_left > 0:
                real = (s.elapsed + s.time_left) / 60
                if abs(real - self.cfg["race_min"]) > 0.1 * self.cfg["race_min"]:
                    self.n = count({**self.cfg, "race_min": real})
            total = (s.elapsed + s.time_left) if s.time_left else self.cfg["race_min"] * 60
            if self.n == 1:
                say(None, L(f"Course courte : un seul relais, {d[self.cur]} va jusqu'au bout.",
                            f"Short race: a single stint, {d[self.cur]} goes to the end."))
                return
            say(None, L(f"Plan de relais : {self.n} relais d'environ {_min(total / self.n)}. Ordre : {order}.",
                        f"Stint plan: {self.n} stints of about {_min(total / self.n)}. Order: {order}."))
            return

        # changement de pilote : le nom dans le jeu change, ou on vient de faire l'arrêt prévu pour ça
        renamed = bool(s.driver and self.last_driver and s.driver != self.last_driver)
        changed = renamed
        if s.pit_stops != self.last_stops:
            self.last_stops = s.pit_stops
            if self.pending:
                changed = True
        self.last_driver = s.driver or self.last_driver
        if changed:
            self._next_stint(s, d, say, renamed)

        self.remaining = s.time_left if s.time_left is not None else max(0.0, self.cfg["race_min"] * 60 - s.elapsed)
        self.driven = max(0.0, s.elapsed - self.stint_start)
        avg = p.avg_lap or s.last_lap or s.best_lap
        full = None
        if avg and p.fuel_per_lap and s.fuel_capacity:
            full = s.fuel_capacity / p.fuel_per_lap * avg       # durée d'un plein complet (s)
        nxt = self._nxt(d)

        if pleins:
            # relais = N pleins : le changement se fait au N-ième arrêt du relais (s'il reste des arrêts)
            self.target = self.cfg["tanks"] * full if full else None
            done_stops = s.pit_stops - self.stops0
            self.pending = bool(p.ready and p.stops_needed and done_stops + 1 >= self.cfg["tanks"])
            self.eng_plan_last_stop = bool(p.ready and not p.stops_needed)
            if eng is not None:
                eng.relay_tyres = self.pending and self.cfg["tyres"]
            if self.pending and not s.in_pits and p.laps_until_box is not None and p.laps_until_box <= 3 and "ann" not in self.said:
                self.said.add("ann")
                n = p.laps_until_box + 1
                say(None, L(f"Changement de pilote à l'arrêt, dans {n} tour{'s' if n > 1 else ''} : {nxt} prend le volant{self._tyres()}.",
                            f"Driver change at the stop, in {n} lap{'s' if n > 1 else ''}: {nxt} takes over{self._tyres()}."))
            return

        left_stints = max(1, self.n - self.done)
        # le temps qui reste est partagé entre les relais restants (celui en cours compris)
        self.target = (self.driven + self.remaining) / left_stints
        if left_stints <= 1 or s.in_pits or not avg:
            self.pending = False
            return
        at_box = self.driven + (p.laps_until_box + 1 - s.lap_frac) * avg if p.laps_until_box is not None else None
        # le prochain plein arrive bien après la fin visée du relais (relais plus courts qu'un plein) :
        # on ne l'attend pas, le changement se fait à l'heure (on en profite pour remettre de l'essence)
        if p.ready and p.stops_needed and at_box is not None and full and at_box <= self.target * 1.15:
            # s'arrêter à ce plein ou au suivant : le plus proche de la durée visée
            self.pending = abs(at_box - self.target) <= abs(at_box + full - self.target)
            if eng is not None:
                eng.relay_tyres = self.pending and self.cfg["tyres"]
            if self.pending and p.laps_until_box <= 3 and "ann" not in self.said:
                self.said.add("ann")
                n = p.laps_until_box + 1
                say(None, L(f"Changement de pilote à l'arrêt, dans {n} tour{'s' if n > 1 else ''} : {nxt} prend le volant{self._tyres()}.",
                            f"Driver change at the stop, in {n} lap{'s' if n > 1 else ''}: {nxt} takes over{self._tyres()}."))
            return
        # pas d'arrêt essence au bon moment : fin du relais à l'heure
        left = self.target - self.driven
        if left <= 5 * avg and "ann" not in self.said:
            self.said.add("ann")
            n = max(1, round(left / avg))
            say(None, L(f"Fin de relais dans {n} tour{'s' if n > 1 else ''}, changement pour {nxt}.",
                        f"End of stint in {n} lap{'s' if n > 1 else ''}, change for {nxt}."))
        if left <= 1.2 * avg:
            self.pending = True
            if eng is not None:
                eng.relay_tyres = self.cfg["tyres"]
            if "box" not in self.said:
                self.said.add("box")
                say(None, L(f"Box ce tour : changement de pilote, {nxt} prend le volant{self._tyres()}.",
                            f"Box this lap: driver change, {nxt} takes over{self._tyres()}."), urgent=True)

    def _match(self, driver: str) -> bool:
        for i, name in enumerate(self.cfg["drivers"]):
            if driver and _same(name, driver):
                self.cur = i
                return True
        return False

    def _next_stint(self, s, d, say, renamed: bool = False) -> None:
        old_target = self.target
        self.done += 1
        prev = self.cur
        # le nom dans le jeu donne le nouveau pilote ; sinon (nom inchangé, ou inconnu) on suit l'ordre prévu
        if not (renamed and self._match(s.driver)) or self.cur == prev:
            k = self._planned(self.done)
            self.cur = k if k is not None else (prev + 1) % len(d)
        self.stint_start, self.pending, self.said = s.elapsed, False, set()
        self.stops0 = s.pit_stops
        if self.cfg["mode"] == "pleins":
            say(None, L(f"Relais {self.done + 1} : {d[self.cur]} au volant, pour {self._tanks()}.",
                        f"Stint {self.done + 1}: {d[self.cur]} driving, for {self._tanks()}."))
            return
        remaining = s.time_left if s.time_left is not None else max(0.0, self.cfg["race_min"] * 60 - s.elapsed)
        left = max(1, self.n - self.done)
        self.target = remaining / left
        msg = L(f"Relais {self.done + 1} sur {self.n} : {d[self.cur]} au volant, pour environ {_min(self.target)}.",
                f"Stint {self.done + 1} of {self.n}: {d[self.cur]} driving, for about {_min(self.target)}.")
        if old_target and abs(self.target - old_target) > 5 * 60:
            msg += L(" Le plan est recalculé.", " The plan has been recalculated.")
        say(None, msg)

    _fullmin = None

    def _planned(self, k: int) -> int | None:
        """Pilote prévu pour le relais k (0 = premier) quand le plan tient compte des indisponibilités."""
        if not self.cfg.get("unavail") or not self.cfg.get("start"):
            return None
        p = plan(self.cfg, tank_minutes(self.cfg, self._fullmin)[0])
        d = names(self.cfg)
        if k < len(p) and p[k].get("start") is not None and p[k]["driver"] in d:
            return d.index(p[k]["driver"])
        return None

    def _nxt(self, d: list[str]) -> str:
        k = self._planned(self.done + 1)
        return d[k] if k is not None else d[(self.cur + 1) % len(d)]

    # ------------------------------------------------------------------ questions / page
    def answer(self) -> str:
        if not self.cfg["on"]:
            return L("Le planning de relais n'est pas activé. Ça se règle dans la page RELAIS du tableau de bord.",
                     "The stint planner is off. You can set it up on the STINTS page of the dashboard.")
        d = names(self.cfg)
        nxt = self._nxt(d)
        order = ", ".join(d[(self.cur + i) % len(d)] for i in range(len(d)))
        if self.stint_start is None:
            if self.cfg["mode"] == "pleins":
                return L(f"Relais de {self._tanks()} chacun. Ordre : {order}.", f"Stints of {self._tanks()} each. Order: {order}.")
            p = plan(self.cfg)
            return L(f"{len(p)} relais prévus, d'environ {_min(self.cfg['race_min'] * 60 / len(p))}. Ordre : {order}.",
                     f"{len(p)} stints planned, about {_min(self.cfg['race_min'] * 60 / len(p))} each. Order: {order}.")
        if self.cfg["mode"] == "pleins":
            if not self.pending and self.eng_plan_last_stop:
                return L(f"Plus de changement de pilote prévu, {d[self.cur]} va jusqu'au bout.",
                         f"No more driver changes planned, {d[self.cur]} goes to the end.")
            k = self.cfg["tanks"] - (self.last_stops - self.stops0 if self.last_stops is not None else 0)
            when = L("au prochain arrêt", "at the next stop") if k <= 1 else L(f"dans {k} arrêts", f"in {k} stops")
            return L(f"Relais {self.done + 1}, {d[self.cur]} au volant. Changement {when}, ensuite c'est {nxt}.",
                     f"Stint {self.done + 1}, {d[self.cur]} driving. Change {when}, then it's {nxt}.")
        if self.n - self.done <= 1:
            return L(f"C'est le dernier relais, {d[self.cur]} va jusqu'au bout.", f"Last stint, {d[self.cur]} goes to the end.")
        left = max(0.0, (self.target or 0) - self.driven)
        return L(f"Relais {self.done + 1} sur {self.n}. Encore environ {_min(left)} pour {d[self.cur]}, ensuite c'est {nxt}.",
                 f"Stint {self.done + 1} of {self.n}. About {_min(left)} more for {d[self.cur]}, then it's {nxt}.")

    eng_plan_last_stop = False

    def ui(self, p=None) -> dict | None:
        """Résumé pour le tableau de bord et la vue téléphone : « Relais 2 · Fred → Laurent au prochain arrêt »."""
        if not self.cfg["on"] or self.stint_start is None:
            return None
        d = names(self.cfg)
        nxt = self._nxt(d)
        if self.cfg["mode"] == "pleins":
            if self.eng_plan_last_stop and not self.pending:
                when = L("jusqu'au bout", "to the end")
                nxt = None
            else:
                k = self.cfg["tanks"] - ((self.last_stops or 0) - self.stops0)
                when = L("au prochain arrêt", "at the next stop") if k <= 1 else L(f"dans {k} arrêts", f"in {k} stops")
        else:
            if self.n - self.done <= 1:
                when, nxt = L("jusqu'au bout", "to the end"), None
            else:
                when = L(f"dans {max(0, round(((self.target or 0) - self.driven) / 60))} min",
                         f"in {max(0, round(((self.target or 0) - self.driven) / 60))} min")
        of = f" / {self.n}" if self.cfg["mode"] == "temps" else ""
        return {"stint": f"{self.done + 1}{of}", "driver": d[self.cur], "next": nxt, "when": when, "soon": self.pending}

    def info(self, p=None, snap=None) -> dict:
        full_min = None
        if p is not None and snap is not None and p.fuel_per_lap and p.avg_lap and getattr(snap, "fuel_capacity", 0):
            full_min = round(snap.fuel_capacity / p.fuel_per_lap * p.avg_lap / 60)
            if full_min >= 5:
                tank_remember(snap, full_min)
        full_min, src = tank_minutes(self.cfg, full_min, snap)
        live = None
        if self.stint_start is not None:
            d = names(self.cfg)
            live = {"stint": self.done + 1, "of": self.n if self.cfg["mode"] == "temps" else None,
                    "driver": d[self.cur], "next": self._nxt(d),
                    "driven_min": round(self.driven / 60),
                    "target_min": round(self.target / 60) if self.target else None,
                    "remaining_min": round((self.remaining or 0) / 60), "pending": self.pending}
        pl = plan(self.cfg, full_min)
        try:
            import share
            hook = bool(share.webhook())
        except Exception:
            hook = False
        return {"cfg": self.cfg, "plan": pl, "fuel_stint_min": full_min, "fuel_src": src, "live": live, "share": share_text(self.cfg, pl),
                "busy": {x: windows(self.cfg, x) for x in names(self.cfg)}, "webhook": hook, "races": races()}


def share_text(cfg: dict, pl: list[dict]) -> str:
    """Le planning, prêt à coller dans le salon Discord de l'équipe."""
    head = "🏁 " + (cfg.get("name") or L("Planning des relais", "Stint plan"))
    if cfg.get("date"):
        y, m, dd = cfg["date"].split("-")
        head += f" · {dd}/{m}/{y}"
    if cfg.get("start"):
        head += L(f" · départ {cfg['start']}", f" · start {cfg['start']}")
    h, mn = divmod(cfg["race_min"], 60)
    head += f" · {h}h{mn:02d}" if mn else f" · {h}h"
    lines = [head]
    for st in pl:
        if st.get("start") is None:
            lines.append(f"{st['n']}. {st['driver']}")
            continue
        when = (f"{st['clock_start']} → {st['clock_end']}" if st.get("clock_start")
                else f"{st['start'] // 60}h{st['start'] % 60:02d} → {st['end'] // 60}h{st['end'] % 60:02d}")
        lines.append(f"{st['n']}. {st['driver']} · {when}" + (" ⚠️" if st.get("clash") else ""))
    if any(st.get("clash") for st in pl):
        lines.append(L("⚠️ personne n'est libre sur ce relais", "⚠️ nobody is free for this stint"))
    lines.append("· Apex Radio")
    return "\n".join(lines)


# ---------------------------------------------------------------------- page RELAIS
def page() -> str:
    import debrief
    t = {k: L(fr, en) for k, (fr, en) in {
        "title": ("PLANNING DES RELAIS", "STINT PLANNER"),
        "intro": ("Pour les courses d'endurance en équipe. Apex annonce les changements de pilote et recalcule le plan "
                  "si un relais dure plus ou moins longtemps que prévu.",
                  "For team endurance races. Apex calls the driver changes and recalculates the plan if a stint runs "
                  "longer or shorter than planned."),
        "on": ("Activer pour la prochaine course", "Use it for the next race"),
        "race": ("Durée de la course", "Race length"), "h": ("h", "h"), "min": ("min", "min"),
        "stint": ("Durée visée d'un relais", "Target stint length"),
        "mode": ("Un relais, c'est", "A stint is"), "mp": ("un nombre de pleins", "a number of tanks"),
        "mt": ("une durée", "a length of time"), "tanks": ("Pleins par relais", "Tanks per stint"),
        "tyres": ("Pneus neufs au changement de pilote", "New tyres at each driver change"),
        "notime": ("Les horaires s'affichent quand Apex connaît la durée d'un plein (après quelques tours sur ce circuit).",
                   "Times show up once Apex knows how long a tank lasts (after a few laps on this track)."),
        "drivers": ("Pilotes, dans l'ordre", "Drivers, in order"),
        "add": ("+ Ajouter un pilote", "+ Add a driver"),
        "save": ("ENREGISTRER", "SAVE"), "saved": ("Enregistré ✓", "Saved ✓"),
        "new": ("Nouvelle course", "New race"),
        "races": ("Mes courses", "My races"), "races_none": ("— aucune course gardée —", "— no saved race —"),
        "races_pick": ("— choisir une course —", "— pick a race —"),
        "keep": ("Garder cette course", "Keep this race"), "kept": ("Course gardée ✓", "Race kept ✓"),
        "drop": ("Supprimer", "Delete"), "drop_sure": ("Sûr ?", "Sure?"), "new_sure": ("Sûr ? Re-clique pour effacer", "Sure? Click again to clear"),
        "plan": ("Le plan", "The plan"), "n": ("Relais", "Stint"), "who": ("Pilote", "Driver"),
        "from": ("Début", "Start"), "to": ("Fin", "End"), "dur": ("Durée", "Length"),
        "live": ("En course", "Live"),
        "fuel": ("Un plein dure environ", "A full tank lasts about"),
        "tankmin": ("Durée d'un plein", "One tank lasts"), "tank_auto": ("auto", "auto"),
        "tank_tip": ("Laisse vide : Apex la mesure en roulant et la retient pour ce circuit.",
                     "Leave empty: Apex measures it while driving and remembers it for this track."),
        "src_manuel": ("(tapée à la main)", "(typed by you)"), "src_live": ("(mesurée en roulant)", "(measured on track)"),
        "src_memo": ("(retenue de ta dernière séance)", "(remembered from your last session)"),
        "fuel2": ("", ""),
        "name": ("Prénom (comme dans le jeu, si possible)", "Name (as in the game, if possible)"),
        "tip": ("Astuce : écris les noms comme dans le jeu, Apex reconnaîtra qui est au volant.",
                "Tip: write the names as in the game, Apex will recognise who is driving."),
        "rname": ("Nom de la course", "Race name"), "rname_ph": ("ex. 6h de Spa", "e.g. Spa 6 Hours"),
        "rdate": ("Date", "Date"), "rstart": ("Heure de départ", "Start time"),
        "busy_ph": ("Pas dispo : 21:50-22:50", "Not free: 21:50-22:50"),
        "busy_tip": ("Indisponibilités : heures où le pilote ne peut pas rouler (ex. 21:50-22:50, 01:00-02:00). "
                     "Il faut l'heure de départ.",
                     "Unavailability: times the driver can't drive (e.g. 21:50-22:50, 01:00-02:00). Needs the start time."),
        "tl": ("Frise", "Timeline"), "share": ("📋 Partager le planning", "📋 Share the plan"),
        "copied": ("✓ Copié ! Colle-le dans Discord (Ctrl+V)", "✓ Copied! Paste it in Discord (Ctrl+V)"),
        "team": ("🚀 Équipe", "🚀 Team"), "clash": ("personne de libre", "nobody free"),
    }.items()}
    body = f"""
<style>
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}}
.f[hidden]{{display:none}} .f{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0}} .f label{{min-width:230px;color:var(--muted)}}
input{{background:#06070B;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font:inherit}}
input[type=number]{{width:70px}} select{{background:#06070B;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font:inherit}} .drv input{{width:220px}} .drv input.busy{{width:230px;font-size:13px}} .drv{{display:flex;gap:6px;margin:6px 0}}
button{{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:999px;padding:7px 14px;font:inherit;cursor:pointer}}
button.main{{background:var(--accent);color:#06070B;border-color:var(--accent);font-weight:700;letter-spacing:.06em}}
#ok{{color:#2BFF88;margin-left:10px}} .big{{font-family:"JetBrains Mono",monospace;font-size:22px;font-weight:700;color:var(--accent)}}
/* style néon, comme les réglages */
h1{{text-shadow:0 0 14px rgba(0,229,255,.55)}}
.card{{--c:0,229,255;border-color:rgba(var(--c),.55);background:linear-gradient(180deg,rgba(var(--c),.07),rgba(var(--c),.015) 60%);
      box-shadow:0 0 16px rgba(var(--c),.18),inset 0 0 10px rgba(var(--c),.06)}}
#livecard{{--c:255,46,136}} .card.scroll{{--c:168,85,247}}
#livecard h2{{color:rgb(255,46,136);text-shadow:0 0 8px rgba(255,46,136,.5)}}
h2{{color:rgb(168,85,247);text-shadow:0 0 8px rgba(168,85,247,.45);letter-spacing:.12em}}
input:focus,select:focus{{outline:none;border-color:rgb(0,229,255);box-shadow:0 0 10px rgba(0,229,255,.35)}}
input[type=checkbox]{{accent-color:rgb(0,229,255);width:17px;height:17px}}
button.main{{box-shadow:0 0 16px rgba(0,229,255,.45)}} button.main:hover{{box-shadow:0 0 24px rgba(0,229,255,.7)}}
#add:hover,.drv button:hover{{border-color:rgb(0,229,255);box-shadow:0 0 10px rgba(0,229,255,.3)}}
th{{color:rgb(168,85,247)}}
.dc0{{color:rgb(0,229,255)}} .dc1{{color:rgb(255,46,136)}} .dc2{{color:rgb(255,210,63)}} .dc3{{color:rgb(61,255,162)}}
#plan td:nth-child(2){{font-weight:700}}
</style>
<h1>{t['title']}</h1><p class="muted">{t['intro']}</p>
<div class="card">
 <div class="f"><label for="on">{t['on']}</label><input type="checkbox" id="on"></div>
 <div class="f"><label>{t['races']}</label><select id="races" style="min-width:260px"></select>
   <button id="keep" style="margin-left:10px">{t['keep']}</button> <button id="dropr">{t['drop']}</button></div>
 <div class="f"><label>{t['rname']}</label><input id="rn" maxlength="60" style="width:260px" placeholder="{t['rname_ph']}"></div>
 <div class="f"><label>{t['rdate']}</label><input type="date" id="rd"> <label style="min-width:0;margin-left:14px">{t['rstart']}</label><input type="time" id="rs"></div>
 <div class="f"><label>{t['race']}</label><input type="number" id="rh" min="0" max="48"> {t['h']}
   <input type="number" id="rm" min="0" max="59" step="5"> {t['min']}</div>
 <div class="f"><label>{t['mode']}</label><select id="mode"><option value="pleins">{t['mp']}</option><option value="temps">{t['mt']}</option></select></div>
 <div class="f" id="rowtanks"><label>{t['tanks']}</label><input type="number" id="tk" min="1" max="10"></div>
 <div class="f" id="rowtm"><label>{t['tankmin']}</label><input type="number" id="tm" min="0" max="300" step="1" placeholder="{t['tank_auto']}"> {t['min']}
   <span class="muted" style="font-size:13px;margin-left:10px">{t['tank_tip']}</span></div>
 <div class="f" id="rowst"><label>{t['stint']}</label><input type="number" id="st" min="10" max="360" step="5"> {t['min']}</div>
 <div class="f"><label for="ty">{t['tyres']}</label><input type="checkbox" id="ty"></div>
 <div class="f" style="align-items:flex-start"><label>{t['drivers']}</label><div><div id="drvs"></div>
   <button id="add">{t['add']}</button><div class="muted" style="font-size:13px;margin-top:6px">{t['tip']}<br>{t['busy_tip']}</div></div></div>
 <div class="f"><button class="main" id="save">{t['save']}</button> <button id="newrace" style="margin-left:10px">{t['new']}</button><span id="ok"></span></div>
</div>
<div class="card" id="livecard" hidden><h2 style="margin-top:0">{t['live']}</h2><div id="live"></div></div>
<h2>{t['plan']}</h2><p class="muted" id="fuel"></p>
<div class="card scroll"><table><thead><tr><th>{t['n']}</th><th>{t['who']}</th><th>{t['from']}</th><th>{t['to']}</th><th>{t['dur']}</th></tr></thead>
<tbody id="plan"></tbody></table></div>
<div class="card" id="tlcard" hidden><h2 style="margin-top:0">{t['tl']}</h2><div id="tl"></div></div>
<div style="margin:12px 0"><button id="sharebtn">{t['share']}</button> <button id="teambtn" hidden>{t['team']}</button> <span id="sharemsg" class="muted"></span></div>
<script>
const T = {json.dumps(t, ensure_ascii=False)};
const $ = id => document.getElementById(id);
const hm = m => Math.floor(m / 60) + "h" + String(m % 60).padStart(2, "0");
let drivers = [], busy = {{}}, shareTxt = "";
function drawDrivers() {{
  $("drvs").innerHTML = "";
  drivers.forEach((d, i) => {{
    const row = document.createElement("div"); row.className = "drv";
    const inp = document.createElement("input"); inp.value = d; inp.placeholder = T.name; inp.maxLength = 24;
    const old = d;
    inp.oninput = () => {{ const v = busy[drivers[i]]; delete busy[drivers[i]]; drivers[i] = inp.value; if (v) busy[inp.value] = v; }};
    const bz = document.createElement("input"); bz.className = "busy"; bz.placeholder = T.busy_ph; bz.maxLength = 120;
    bz.value = busy[d] || ""; bz.oninput = () => {{ busy[drivers[i]] = bz.value; }};
    const del = document.createElement("button"); del.textContent = "✕";
    del.onclick = () => {{ drivers.splice(i, 1); drawDrivers(); }};
    row.append(inp, bz, del); $("drvs").append(row);
  }});
}}
function draw(d, form) {{
  drawRaces(d.races || [], (d.cfg.name || "").trim());
  if (form) {{
    $("on").checked = d.cfg.on; $("rh").value = Math.floor(d.cfg.race_min / 60); $("rm").value = d.cfg.race_min % 60;
    $("st").value = d.cfg.stint_min; $("tk").value = d.cfg.tanks; $("tm").value = d.cfg.tank_min || ""; $("ty").checked = d.cfg.tyres; $("mode").value = d.cfg.mode; modeRows();
    busy = Object.assign({{}}, d.cfg.unavail || {{}});
    $("rn").value = d.cfg.name || ""; $("rd").value = d.cfg.date || ""; $("rs").value = d.cfg.start || "";
    drivers = d.cfg.drivers.length ? d.cfg.drivers.slice() : ["", ""]; drawDrivers();
  }}
  const known = d.plan.length && d.plan[0].start !== null;
  const order = [];
  $("plan").innerHTML = d.plan.map(p => {{ if (!order.includes(p.driver)) order.push(p.driver); return `<tr><td>${{p.n}}</td><td class="dc${{order.indexOf(p.driver) % 4}}">${{p.driver.replace(/</g, "&lt;")}}</td><td>${{known ? (p.clock_start || hm(p.start)) : "–"}}</td><td>${{known ? (p.clock_end || hm(p.end)) : "–"}}${{p.clash ? " ⚠️" : ""}}</td><td>${{known ? (p.end - p.start) + " min" : (d.cfg.mode === "pleins" ? d.cfg.tanks + " ⛽" : "–")}}</td></tr>`; }}).join("");
  shareTxt = d.share || ""; drawTL(d, known, order); $("teambtn").hidden = !d.webhook;
  $("fuel").textContent = d.fuel_stint_min ? `${{T.fuel}} ${{d.fuel_stint_min}} min ${{T["src_" + d.fuel_src] || ""}}.` : (known ? "" : T.notime);
  $("livecard").hidden = !d.live;
  if (d.live) $("live").innerHTML = `<span class="big">${{T.n}} ${{d.live.stint}}${{d.live.of ? " / " + d.live.of : ""}}</span> · ${{d.live.driver.replace(/</g, "&lt;")}} · ${{d.live.driven_min}}${{d.live.target_min ? " / " + d.live.target_min : ""}} min → ${{d.live.next.replace(/</g, "&lt;")}}`;
}}
const COLORS = ["0,229,255", "255,46,136", "255,210,63", "61,255,162"];
function drawTL(d, known, order) {{
  if (!known) {{ $("tlcard").hidden = true; return; }}
  $("tlcard").hidden = false;
  const total = d.cfg.race_min, W = 1000, rowH = 34, left = 130;
  const names = d.cfg.drivers.length ? d.cfg.drivers : order;
  const t0 = d.cfg.start ? (+d.cfg.start.slice(0, 2)) * 60 + (+d.cfg.start.slice(3, 5)) : null;
  const x = m => left + (W - left - 10) * Math.min(1, m / total);
  let svg = `<svg viewBox="0 0 ${{W}} ${{(names.length + 1) * rowH + 24}}" style="width:100%;height:auto">`;
  const step = total > 600 ? 120 : 60;
  for (let m = 0; m <= total; m += step) {{
    const lab = t0 != null ? String(Math.floor((t0 + m) % 1440 / 60)).padStart(2, "0") + ":" + String((t0 + m) % 60).padStart(2, "0") : Math.floor(m / 60) + "h";
    svg += `<line x1="${{x(m)}}" y1="16" x2="${{x(m)}}" y2="${{(names.length + 1) * rowH + 10}}" stroke="rgba(255,255,255,.08)"/>`
         + `<text x="${{x(m)}}" y="12" fill="#8892A6" font-size="11" text-anchor="${{m + step > total ? "end" : "middle"}}" font-family="JetBrains Mono,monospace">${{lab}}</text>`;
  }}
  names.forEach((nm, i) => {{
    const y = 22 + i * rowH, c = COLORS[i % 4];
    svg += `<text x="6" y="${{y + 20}}" fill="rgb(${{c}})" font-size="14" font-weight="700">${{nm.replace(/</g, "&lt;")}}</text>`;
    (d.busy || {{}})[nm] && d.busy[nm].forEach(([a, b]) => {{
      svg += `<rect x="${{x(a)}}" y="${{y + 4}}" width="${{Math.max(2, x(b) - x(a))}}" height="${{rowH - 10}}" fill="rgba(255,255,255,.07)" stroke="rgba(255,255,255,.25)" stroke-dasharray="4 3" rx="5"/>`;
    }});
    d.plan.filter(p => p.driver === nm).forEach(p => {{
      svg += `<rect x="${{x(p.start)}}" y="${{y + 4}}" width="${{Math.max(3, x(p.end) - x(p.start) - 2)}}" height="${{rowH - 10}}" rx="5" fill="rgba(${{c}},.85)" style="filter:drop-shadow(0 0 5px rgba(${{c}},.6))"/>`
           + `<text x="${{x(p.start) + 6}}" y="${{y + 21}}" fill="#06070B" font-size="12" font-weight="700">${{p.n}}</text>`;
    }});
  }});
  svg += "</svg>";
  $("tl").innerHTML = svg;
}}
$("sharebtn").onclick = async () => {{
  let ok = false;
  try {{ await navigator.clipboard.writeText(shareTxt); ok = true; }} catch (_) {{
    const a = document.createElement("textarea"); a.value = shareTxt; document.body.appendChild(a); a.select();
    try {{ ok = document.execCommand("copy"); }} catch (__) {{}} a.remove(); }}
  $("sharemsg").textContent = ok ? T.copied : "";
  if (ok) fetch("/api/share/open", {{ method: "POST", body: "{{}}" }});
}};
$("teambtn").onclick = async () => {{
  $("sharemsg").textContent = "…";
  let ok = false;
  try {{ ok = (await (await fetch("/api/share/text", {{ method: "POST", body: JSON.stringify({{ text: shareTxt }}) }})).json()).ok; }} catch (_) {{}}
  $("sharemsg").textContent = ok ? "✓" : "✗";
}};
async function load(form) {{ draw(await (await fetch("/api/relais")).json(), form); }}
function modeRows() {{ const p = $("mode").value === "pleins"; $("rowtanks").hidden = !p; $("rowtm").hidden = !p; $("rowst").hidden = p; }}
$("mode").onchange = modeRows;
$("add").onclick = () => {{ if (drivers.length < 8) {{ drivers.push(""); drawDrivers(); }} }};
$("save").onclick = async () => {{
  const cfg = {{ on: $("on").checked, race_min: (+$("rh").value || 0) * 60 + (+$("rm").value || 0), stint_min: +$("st").value, tanks: +$("tk").value, tank_min: +$("tm").value || 0, tyres: $("ty").checked, mode: $("mode").value, drivers,
    name: $("rn").value, date: $("rd").value, start: $("rs").value, unavail: busy }};
  draw(await (await fetch("/api/relais", {{ method: "POST", body: JSON.stringify(cfg) }})).json(), true);
  $("ok").textContent = T.saved; setTimeout(() => $("ok").textContent = "", 2500);
}};
// Nouvelle course : on efface nom, date, heure et indisponibilités (on garde les pilotes et les réglages de relais)
let armNew = null;
$("newrace").onclick = () => {{
  if (!armNew) {{
    $("newrace").textContent = T.new_sure;
    armNew = setTimeout(() => {{ armNew = null; $("newrace").textContent = T.new; }}, 4000);
    return;
  }}
  clearTimeout(armNew); armNew = null; $("newrace").textContent = T.new;
  $("rn").value = ""; $("rd").value = ""; $("rs").value = ""; $("on").checked = false;
  Object.keys(busy).forEach(k => delete busy[k]);
  drawDrivers();
  $("save").click();
}};
// Mes courses : garder la course affichée, en recharger une autre, en supprimer une
function drawRaces(list, current) {{
  const sel = $("races"); if (document.activeElement === sel) return;
  sel.innerHTML = "";
  const o0 = document.createElement("option"); o0.value = ""; o0.textContent = list.length ? T.races_pick : T.races_none; sel.appendChild(o0);
  list.forEach(r => {{ const o = document.createElement("option"); o.value = r.key;
    o.textContent = r.name + (r.date ? " · " + r.date.split("-").reverse().join("/") : "") + (r.start ? " · " + r.start : "");
    if (r.key === current) o.selected = true; sel.appendChild(o); }});
  $("dropr").disabled = !sel.value;
}}
async function raceAction(body) {{ draw(await (await fetch("/api/relais", {{ method: "POST", body: JSON.stringify(body) }})).json(), true); }}
$("races").onchange = () => {{ $("dropr").disabled = !$("races").value; if ($("races").value) raceAction({{ _race: "load", key: $("races").value }}); }};
$("keep").onclick = async () => {{
  const cfg = {{ on: $("on").checked, race_min: (+$("rh").value || 0) * 60 + (+$("rm").value || 0), stint_min: +$("st").value, tanks: +$("tk").value, tank_min: +$("tm").value || 0, tyres: $("ty").checked, mode: $("mode").value, drivers,
    name: $("rn").value, date: $("rd").value, start: $("rs").value, unavail: busy }};
  await raceAction(Object.assign({{ _race: "store" }}, cfg));
  $("ok").textContent = T.kept; setTimeout(() => $("ok").textContent = "", 2500);
}};
let armDrop = null;
$("dropr").onclick = () => {{
  const k = $("races").value; if (!k) return;
  if (!armDrop) {{ $("dropr").textContent = T.drop_sure; armDrop = setTimeout(() => {{ armDrop = null; $("dropr").textContent = T.drop; }}, 4000); return; }}
  clearTimeout(armDrop); armDrop = null; $("dropr").textContent = T.drop;
  raceAction({{ _race: "drop", key: k }});
}};
load(true); setInterval(() => load(false), 5000);
</script>"""
    return debrief._page(L("Relais", "Stints"), body)
