"""
Tactique de course :
- Penalties : annonce des pénalités à purger (drive-through / stop-go) et des tours qui restent.
- Undercut  : quand la voiture devant / derrière s'arrête, ou quand tu peux tenter de la passer au stand.
- Pace      : tous les 5 tours propres, une phrase sur ton rythme, ta régularité et l'usure.
- FuelBook  : mémorise ta conso et la durée des courses par circuit pour calculer l'essence de départ.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path

from i18n import L, dec
from phrases import pick

HERE = Path(__file__).parent
from paths import DATA, LOCAL  # noqa: E402
FUELBOOK = DATA / "fuelbook.json"
PENALTY_LAPS = 3          # LMU laisse normalement 3 tours pour purger une pénalité
TACTIC_GAP = 45.0         # s : au plus une annonce tactique toutes les 45 s
PACE_EVERY = 5


def _lap(t: float) -> str:
    m, r = divmod(t, 60)
    return dec(f"{int(m)} minute {r:.1f}") if m else dec(L(f"{r:.1f} secondes", f"{r:.1f} seconds"))


def _dix(x: float) -> str:
    d = round(abs(x) * 10)
    if d >= 10:
        return dec(L(f"{abs(x):.1f} seconde" + ("s" if abs(x) >= 2 else ""), f"{abs(x):.1f} seconds"))
    return L(f"{max(1, d)} dixième" + ("s" if d > 1 else ""), f"{max(1, d)} tenth" + ("s" if d > 1 else ""))


# ===================================================================== pénalités
class Penalties:
    def __init__(self) -> None:
        self.count = 0
        self.given_lap = None
        self.said_lap = None
        self.key = None

    def update(self, s, say) -> None:
        if not s.on_track:
            return
        key = (s.track, s.session_code)
        if key != self.key:
            self.key, self.count, self.given_lap = key, s.penalties, (s.laps_done if s.penalties else None)
            return
        n = s.penalties
        if n > self.count:
            self.given_lap = self.said_lap = s.laps_done
            say(None, L("Pénalité ! Il faut la purger aux stands, regarde l'écran pour savoir si c'est un drive-through "
                        f"ou un stop and go. Normalement tu as {PENALTY_LAPS} tours.",
                        "Penalty! You need to serve it in the pits, check the screen for drive-through or stop and go. "
                        f"You normally have {PENALTY_LAPS} laps."), urgent=True)
        elif n < self.count:
            if n == 0:
                self.given_lap = None
                say(None, pick("pen_ok", [("Pénalité purgée, c'est bon.", "Penalty served, all good."),
                                          ("C'est bon, pénalité effacée. On repart.", "Done, penalty cleared. Let's go."),
                                          ("Pénalité purgée, on n'en parle plus. Remets du rythme.", "Penalty served, forget it. Build the pace back up.")]))
            else:
                say(None, L(f"Une pénalité purgée, il en reste {n}.", f"One penalty served, {n} left."))
        elif n and self.given_lap is not None and s.laps_done != self.said_lap and not s.in_pits:
            self.said_lap = s.laps_done
            left = PENALTY_LAPS - (s.laps_done - self.given_lap)
            if left == 1:
                say(None, L("Dernier tour pour purger la pénalité, rentre au stand à la fin de ce tour !",
                            "Last lap to serve the penalty, box at the end of this lap!"), urgent=True)
            elif left > 1:
                say(None, pick("pen_left", [(f"Pénalité toujours à purger, plus que {left} tours.", f"Penalty still to serve, {left} laps left."),
                                            (f"N'oublie pas la pénalité : il te reste {left} tours pour la faire.", f"Don't forget the penalty: {left} laps left to serve it."),
                                            (f"Rappel, pénalité à purger dans les {left} prochains tours.", f"Reminder, penalty to serve within {left} laps.")]))
        self.count = n

    def ui(self, s) -> dict:
        left = None
        if s.penalties and self.given_lap is not None:
            left = max(0, PENALTY_LAPS - (s.laps_done - self.given_lap))
        return {"count": s.penalties, "laps_left": left}


# ===================================================================== undercut / overcut
class Undercut:
    def __init__(self) -> None:
        self.prev = {"ahead": (None, False), "behind": (None, False)}
        self.stint = None
        self.offered = False
        self.pitted = set()     # voitures déjà passées au stand pendant ce relais
        self.last = -99.0

    def _say(self, say, text: str) -> None:
        now = time.monotonic()
        if now - self.last < TACTIC_GAP:
            return
        self.last = now
        say(None, text)

    def update(self, s, plan, say) -> None:
        if not s.on_track or s.session != "course" or s.game_phase != 5:
            self.prev = {"ahead": (None, False), "behind": (None, False)}
            return
        if s.pit_stops != self.stint:
            self.stint, self.offered, self.pitted = s.pit_stops, False, set()
        for side in ("ahead", "behind"):
            car = getattr(s, side) or {}
            name, pits = car.get("name"), bool(car.get("in_pits"))
            pname, ppits = self.prev[side]
            self.prev[side] = (name, pits)
            if s.in_pits or not name or name != pname or not pits or ppits:
                continue
            # cette voiture vient d'entrer au stand
            self.pitted.add(name)
            if side == "ahead":
                self._ahead_pits(s, plan, say, name)
            else:
                self._behind_pits(s, plan, say)
        # avant que la voiture devant ne s'arrête : tenter l'undercut ?
        if (not self.offered and plan.ready and plan.stops_needed and plan.laps_until_box in (2, 3)
                and plan.change_tyres and s.gap_class_ahead and s.gap_class_ahead < 2.5
                and s.ahead and not s.ahead.get("in_pits") and s.ahead.get("name") not in self.pitted):
            self.offered = True
            self._say(say, L(f"Tu es à {dec(f'{s.gap_class_ahead:.1f}')} seconde de {s.ahead.get('name') or 'la voiture devant'}. "
                             "Si tu rentres un tour avant lui avec des pneus neufs, tu peux le passer à l'undercut. "
                             "Demande-moi de préparer le stand si tu veux y aller.",
                             f"You're {s.gap_class_ahead:.1f} seconds behind {s.ahead.get('name') or 'the car ahead'}. "
                             "Pit a lap before him on new tyres and you can undercut him. "
                             "Ask me to prepare the pit stop if you want to go for it."))

    def _ahead_pits(self, s, plan, say, name) -> None:
        if not plan.ready:
            return
        if not plan.stops_needed:
            self._say(say, L(f"{name} rentre au stand. Toi tu vas au bout sans t'arrêter : tu prends sa place.",
                             f"{name} is pitting. You go to the end without stopping: you take his place."))
        elif plan.laps_until_box is not None and plan.laps_until_box >= 2:
            n = min(plan.laps_until_box, 3)
            self._say(say, L(f"{name} rentre au stand. Pousse à fond les {n} prochains tours pendant qu'il ressort "
                             "avec des pneus froids : tu peux le passer à l'overcut.",
                             f"{name} is pitting. Push hard for the next {n} laps while he's on cold tyres: "
                             "you can overcut him."))
        else:
            self._say(say, L(f"{name} rentre au stand en même temps que toi. Arrêt propre et sortie des stands "
                             "nickel, tu peux ressortir devant.",
                             f"{name} is pitting at the same time. Clean stop and a tidy pit exit, you can come out ahead."))

    def _behind_pits(self, s, plan, say) -> None:
        if not plan.ready or not plan.stops_needed or plan.laps_until_box is None:
            return
        g = s.gap_class_behind
        if g is not None and g < 5 and plan.laps_until_box <= 3:
            self._say(say, L(f"La voiture derrière rentre au stand, elle était à {dec(f'{g:.1f}')} seconde. "
                             "Rentre au prochain tour pour couvrir l'undercut, ou pousse fort ce tour-ci.",
                             f"The car behind is pitting, it was {g:.1f} seconds back. "
                             "Box next lap to cover the undercut, or push hard this lap."))


# ===================================================================== rythme
class Pace:
    def __init__(self) -> None:
        self.done = 0
        self.key = None
        self.blocks = []        # pour le débrief : [(tours, moyenne, écart type)]

    def update(self, s, eng, say) -> None:
        if not s.on_track:
            return
        key = (s.track, s.session_code)
        if key != self.key:
            self.key, self.done, self.blocks = key, 0, []
        if s.session != "course" or s.game_phase != 5:
            return
        laps = [l.time for l in eng.laps if l.time and not l.dirty and l.number > 0]
        best = min(laps) if laps else None
        laps = [t for t in laps if best and t < best * 1.05]      # pas les tours avec incident
        n = len(laps) // PACE_EVERY
        if n <= self.done:
            return
        self.done = n
        last = laps[-PACE_EVERY:]
        prev = laps[-2 * PACE_EVERY:-PACE_EVERY] if len(laps) >= 2 * PACE_EVERY else None
        med, sd = statistics.median(last), statistics.pstdev(last)
        self.blocks.append((len(laps), med, sd))
        parts = [L(f"Rythme moyen {_lap(med)} sur tes 5 derniers tours", f"Average pace {_lap(med)} over your last 5 laps")]
        if prev:
            d = med - statistics.median(prev)
            if d > 0.25:
                wear = min(s.tyre_wear) * 100 if s.tyre_wear else None
                parts.append(L(f"tu perds {_dix(d)} par tour par rapport aux 5 d'avant", f"you're losing {_dix(d)} a lap versus the 5 before")
                             + (L(f", les pneus sont à {wear:.0f} %", f", tyres at {wear:.0f} %") if wear is not None else ""))
            elif d < -0.25:
                parts.append(L(f"tu as gagné {_dix(d)} par tour, continue", f"you've gained {_dix(d)} a lap, keep it up"))
            else:
                parts.append(L("rythme stable", "steady pace"))
        if sd < 0.3:
            parts.append(L("très régulier", "very consistent"))
        elif sd > 0.8:
            parts.append(L("un peu irrégulier, vise la régularité", "a bit inconsistent, aim for consistency"))
        say(None, ", ".join(parts) + ".")


# ===================================================================== essence de départ
class FuelBook:
    def __init__(self) -> None:
        try:
            self.data = json.loads(FUELBOOK.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        self._race_key = None
        self._last_save = 0.0

    def _save(self) -> None:
        try:
            FUELBOOK.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def update(self, s, plan, eng, say=None) -> None:
        if say:
            self.pre_race(s, say)
        if not s.on_track or not s.track or s.in_pits:
            return
        d = self.data.setdefault(s.track, {})
        changed = False
        clean = [l for l in eng.laps if l.time and not l.dirty and l.number > 0]
        if plan.fuel_per_lap and len(clean) >= 3 and s.raining < 0.1:
            if plan.energy_per_lap:
                d["epl"] = round(plan.energy_per_lap, 4)
            d.update({"fpl": round(plan.fuel_per_lap, 3), "avg": round(plan.avg_lap or 0, 3) or d.get("avg"),
                      "cap": s.fuel_capacity or d.get("cap"), "car": s.car, "class": s.car_class,
                      "date": time.strftime("%d/%m/%Y")})
            changed = True
        if s.session == "course" and s.game_phase == 5 and (s.track, s.session_code) != self._race_key:
            self._race_key = (s.track, s.session_code)
            if s.max_laps:
                d["race_laps"] = s.max_laps
                d.pop("race_min", None)
            elif s.time_left:
                d["race_min"] = int(round((s.elapsed + s.time_left) / 60))
                d.pop("race_laps", None)
            changed = True
        if changed and time.monotonic() - self._last_save > 30:
            self._last_save = time.monotonic()
            self._save()

    # ------------------------------------------------------- avant le départ
    def need(self, s) -> dict | None:
        """Ce qu'il faut pour la course : tours, litres (et énergie). Durée lue dans la session en cours si c'est
        la course, sinon la dernière course connue sur ce circuit. None si on ne sait pas encore."""
        d = self.data.get(s.track, {}) if s.track else {}
        fpl, avg = d.get("fpl"), d.get("avg")
        if not fpl:
            return None
        laps = None
        if s.session == "course" and s.max_laps:
            laps = s.max_laps
        elif s.session == "course" and s.time_left and avg and s.game_phase < 5:
            laps = math.ceil(s.time_left / avg)
        elif d.get("race_laps"):
            laps = d["race_laps"]
        elif d.get("race_min") and avg:
            laps = math.ceil(d["race_min"] * 60 / avg)
        if not laps:
            return None
        cap = s.fuel_capacity or d.get("cap")
        litres = math.ceil((laps + 1) * fpl)        # + 1 tour : tour de formation et marge
        stop = bool(cap and litres > cap)
        energy = None
        if s.energy is not None and d.get("epl"):
            e = (laps + 1) * d["epl"]
            stop = stop or e > 1.0
            energy = min(1.0, e)
        return {"laps": laps, "litres": min(litres, int(cap)) if cap else litres, "stop": stop, "cap": cap, "energy": energy}

    def brief(self, s) -> str:
        """Réponse à « combien d'essence pour la course ? »."""
        n = self.need(s)
        if n is None:
            d = self.data.get(s.track, {}) if s.track else {}
            if not d.get("fpl"):
                return L("Je ne connais pas encore ta conso sur ce circuit. Fais au moins 3 tours propres, en essais par exemple.",
                         "I don't know your consumption on this track yet. Do at least 3 clean laps, in practice for example.")
            return L("Je ne connais pas la durée de la course. Indique-la dans l'Atelier.",
                     "I don't know the race length. Enter it in the Workshop.")
        laps = n["laps"]
        if n["energy"] is not None:
            need_txt = L(f"Pour {laps} tours, il te faut {n['energy'] * 100:.0f} % d'énergie.",
                         f"For {laps} laps, you need {n['energy'] * 100:.0f} % energy.")
            have = s.energy * 100 if s.energy is not None else None
            unit_fr, unit_en, want = " %", " %", n["energy"] * 100
        else:
            need_txt = L(f"Pour {laps} tours, il te faut {n['litres']} litres.", f"For {laps} laps, you need {n['litres']} litres.")
            have, unit_fr, unit_en, want = s.fuel, " litres", " litres", n["litres"]
        out = need_txt
        if n["stop"]:
            out = L(f"Pour {laps} tours, un plein ne suffit pas : pars le réservoir plein, il faudra un arrêt.",
                    f"For {laps} laps, one tank isn't enough: start full, you'll need a stop.")
            return out
        if have and s.session == "course" and s.game_phase < 5:
            diff, pct = have - want, unit_fr == " %"
            h, x = round(have), round(abs(diff))
            if diff >= (5 if pct else 3):
                out += " " + (L(f"Tu as {h} % d'énergie, tu peux en enlever {x} %, la voiture sera plus légère.",
                                f"You have {h} % energy, you can take off {x} %, the car will be lighter.") if pct else
                              L(f"Tu as {h} litres, tu peux en enlever {x}, la voiture sera plus légère.",
                                f"You have {h} litres, you can take off {x}, the car will be lighter."))
            elif diff < -1:
                out += " " + (L(f"Attention, tu n'as que {h} % d'énergie, rajoute {x} %.",
                                f"Careful, you only have {h} % energy, add {x} %.") if pct else
                              L(f"Attention, tu n'as que {h} litres, rajoute-en {x}.",
                                f"Careful, you only have {h} litres, add {x}."))
            else:
                out += " " + L("Tu as ce qu'il faut, c'est bon.", "You've got what you need, all good.")
        return out

    def pre_race(self, s, say) -> None:
        """Une fois par course, avant le départ : prévient si tu pars avec trop (ou pas assez) d'essence."""
        if s.session != "course" or s.game_phase >= 5 or not s.on_track or not s.track or not s.fuel:
            return
        key = (s.track, s.session_code, "depart")
        if getattr(self, "_pre_key", None) == key:
            return
        n = self.need(s)
        if n is None:
            return
        self._pre_key = key
        if n["stop"]:
            return                              # course plus longue qu'un plein : rien à enlever
        if n["energy"] is not None:
            diff = (s.energy or 0) * 100 - n["energy"] * 100
            if diff >= 5 or diff < -1:
                say(None, self.brief(s))
        else:
            diff = s.fuel - n["litres"]
            if diff >= 3 or diff < -1:
                say(None, self.brief(s))

    def set_race(self, track: str, minutes: int | None, laps: int | None = None) -> None:
        d = self.data.setdefault(track, {})
        d.pop("race_min", None); d.pop("race_laps", None)
        if laps:
            d["race_laps"] = int(laps)
        elif minutes:
            d["race_min"] = int(minutes)
        self._save()

    def suggest(self, track: str) -> dict:
        d = self.data.get(track, {})
        out = {"fpl": d.get("fpl"), "avg": d.get("avg"), "race_min": d.get("race_min"), "race_laps": d.get("race_laps"),
               "cap": d.get("cap"), "litres": None, "laps": None, "why": ""}
        fpl, avg = d.get("fpl"), d.get("avg")
        if not fpl:
            out["why"] = L("Fais au moins 3 tours propres sur ce circuit pour que je mesure ta conso.",
                           "Do at least 3 clean laps on this track so I can measure your consumption.")
            return out
        if d.get("race_laps"):
            laps = d["race_laps"]
        elif d.get("race_min") and avg:
            laps = math.ceil(d["race_min"] * 60 / avg)
        else:
            out["why"] = L("Indique la durée de la course pour calculer l'essence de départ.",
                           "Enter the race length to work out the starting fuel.")
            return out
        litres = math.ceil((laps + 1) * fpl)        # + 1 tour : tour de formation et marge
        cap = d.get("cap")
        stop = bool(cap and litres > cap)
        if stop:
            litres = int(cap)
        out.update({"laps": laps, "litres": litres, "stop": stop,
                    "why": dec(L(f"{laps} tours × {fpl:.2f} L + 1 tour de marge", f"{laps} laps × {fpl:.2f} L + 1 lap margin")
                               + (L(" — plus que le réservoir : plein, et un arrêt sera nécessaire",
                                    " — more than the tank: full tank, and a stop will be needed") if stop else ""))})
        return out
