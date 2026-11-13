"""
Menu des stands de LMU (étape 4) : Jessica règle l'arrêt toute seule.

Lecture  : GET  /rest/garage/PitMenu/receivePitMenu  (liste des lignes du menu)
Écriture : POST /rest/garage/PitMenu/loadPitMenu     (même liste, valeurs modifiées)
Chaque ligne : {"PMC Value": id, "name": "FUEL:", "currentSetting": index, "settings": [{"text": ...}, ...]}
  id 7  = essence (niveau voulu APRÈS l'arrêt, ex. "41l/15 laps")
  id 8  = pneus (0 = "Aucun changement", puis "Neuf Medium", "Neuf Mouillé"...)
  id 2  = réparations
Après écriture on relit le menu pour vérifier que LMU a bien pris les valeurs.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request

from i18n import L

BASE = "http://localhost:6397"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
FUEL, TIRES, DAMAGE = 7, 8, 2
WHEELS = (13, 14, 15, 16)   # FL TIRE, FR TIRE, RL TIRE, RR TIRE : un pneu à la fois


def _req(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json", "Accept": "application/json"})
    with _OPENER.open(r, timeout=3) as resp:
        raw = resp.read().decode("utf-8", "replace")
        return resp.status, (json.loads(raw) if raw.strip().startswith(("[", "{")) else raw)


def read_menu() -> list:
    status, j = _req("GET", "/rest/garage/PitMenu/receivePitMenu")
    return j if isinstance(j, list) else []


def _item(menu: list, pmc: int):
    return next((it for it in menu if it.get("PMC Value") == pmc), None)


def _liters(text: str) -> float | None:
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)", text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def plan_menu(menu: list, fuel_total: float | None, tyres: str | None, compound: str, repair) -> tuple[list, list]:
    """repair : None = on ne touche pas, False = « Ne pas réparer », "body" = carrosserie, "all" = tout réparer."""
    """Retourne (menu modifié, liste de ce qui change en clair). tyres : None/"keep"/"same"/"Wet"/"dry"."""
    menu = json.loads(json.dumps(menu))   # copie
    changes = []
    it = _item(menu, FUEL)
    if it and fuel_total == 0:   # le pilote a dit « pas d'essence » : niveau le plus bas = on n'ajoute rien
        opts = [(i, _liters(s.get("text"))) for i, s in enumerate(it["settings"])]
        opts = [(i, l) for i, l in opts if l is not None]
        if opts:
            it["currentSetting"] = min(opts, key=lambda o: o[1])[0]
            changes.append(L("pas d'essence", "no fuel"))
    elif it and fuel_total is not None:
        opts = [(i, _liters(s.get("text"))) for i, s in enumerate(it["settings"])]
        opts = [(i, l) for i, l in opts if l is not None]
        if opts:
            # plus petit niveau qui couvre le besoin, sinon le plein
            ok = [o for o in opts if o[1] >= fuel_total]
            idx, lit = min(ok, key=lambda o: o[1]) if ok else max(opts, key=lambda o: o[1])
            if it["currentSetting"] != idx:
                it["currentSetting"] = idx
            changes.append(L(f"essence à {lit:.0f} litres", f"fuel to {lit:.0f} litres"))
    it = _item(menu, TIRES)
    if isinstance(tyres, tuple):   # ordre du pilote, pneu par pneu
        return _plan_wheels(menu, tyres, compound, changes, repair)
    if it and tyres:
        idx = 0
        if tyres != "keep":
            want = None if tyres in ("same", "dry") else tyres
            cur = (compound or "").strip().lower()
            for i, s in enumerate(it["settings"]):
                t, typ = s.get("text", ""), (s.get("type") or "")
                if i == 0 or s.get("isUsed") or "INVALID" in t.upper():
                    continue
                if want == "Wet" and typ == "Wet":
                    idx = i; break
                if tyres == "same" and typ.lower() == cur:
                    idx = i; break
                if tyres == "dry" and typ != "Wet":
                    idx = i; break
            if idx == 0 and tyres == "same":   # composé actuel introuvable : premier pneu sec neuf
                idx = next((i for i, s in enumerate(it["settings"]) if i and not s.get("isUsed") and s.get("type") != "Wet"
                            and "INVALID" not in s.get("text", "").upper()), 0)
        it["currentSetting"] = idx
        typ = (it["settings"][idx].get("type") or "") if idx else ""
        changes.append(L("on garde les pneus", "keep the tyres") if idx == 0 else L("pneus pluie neufs", "new wet tyres") if typ == "Wet"
                       else L(f"pneus neufs {typ.lower()}", f"new {typ.lower()} tyres").strip())
    return _plan_damage(menu, changes, repair)


def _plan_damage(menu: list, changes: list, repair) -> tuple[list, list]:
    it = _item(menu, DAMAGE)
    if it and repair:
        print(f"  Menu stand, réparations possibles : {[s.get('text') for s in it.get('settings', [])]}")
    if it and repair and len(it["settings"]) > 1:
        opts = [(i, s.get("text", "").lower()) for i, s in enumerate(it["settings"])]
        opts = [(i, t) for i, t in opts
                if ("répar" in t or "repair" in t or "fix" in t) and not any(n in t for n in ("ne pas", "not", "no ", "aucun"))]
        # LMU : « Ne pas réparer », « Réparer la carrosserie », « Tout réparer »
        want_all = repair == "all"
        pick = next((o for o in opts if any(k in o[1] for k in (("tout", "all", "full") if want_all else ("carross", "body", "aero")))), None)
        pick = pick or (opts[-1] if want_all and opts else opts[0] if opts else None)
        if pick:
            it["currentSetting"] = pick[0]
            got_all = any(k in pick[1] for k in ("tout", "all", "full"))   # certaines voitures (GT3) n'ont pas « Tout réparer »
            changes.append(L("on répare tout", "full repairs") if got_all else L("réparation de la carrosserie", "bodywork repairs"))
    if it and repair is False and len(it["settings"]) > 1:   # le pilote a dit « pas de réparation »
        idx = next((i for i, s in enumerate(it["settings"])
                    if any(n in s.get("text", "").lower() for n in ("ne pas", "pas de", "not", "no ", "none", "aucun"))), 0)
        it["currentSetting"] = idx
        changes.append(L("pas de réparation", "no repairs"))
    return menu, changes


def _new_tyre_index(settings: list, compound: str) -> int:
    """Indice du pneu neuf du même type que celui monté (sinon le premier sec neuf)."""
    cur = (compound or "").strip().lower()
    ok = [(i, s) for i, s in enumerate(settings)
          if i and not s.get("isUsed") and "INVALID" not in s.get("text", "").upper() and "mixte" not in s.get("text", "").lower()]
    same = next((i for i, s in ok if cur and (cur in (s.get("type") or "").lower() or cur in s.get("text", "").lower())), None)
    dry = next((i for i, s in ok if (s.get("type") or "") != "Wet" and "mouill" not in s.get("text", "").lower()), None)
    return same or dry or 0


def _plan_wheels(menu: list, wheels: tuple, compound: str, changes: list, repair) -> tuple[list, list]:
    from questions import wheels_text
    per = [_item(menu, pmc) for pmc in WHEELS]
    allw = _item(menu, TIRES)
    if wheels and len(wheels) < 4 and not all(per):
        changes.append(L("pas de choix pneu par pneu sur cette voiture, je change les quatre",
                         "no tyre-by-tyre choice on this car, changing all four"))
        wheels = (0, 1, 2, 3)
    if allw is not None:
        if not wheels:
            allw["currentSetting"] = 0
        elif len(wheels) == 4:
            allw["currentSetting"] = _new_tyre_index(allw["settings"], compound)
        else:   # « Pneus mixtes » : c'est la ligne de chaque roue qui compte
            mixed = next((i for i, s in enumerate(allw["settings"]) if "mixte" in s.get("text", "").lower()
                          or "mixed" in s.get("text", "").lower()), None)
            if mixed is not None:
                allw["currentSetting"] = mixed
    for k, it in enumerate(per):
        if it:
            it["currentSetting"] = _new_tyre_index(it["settings"], compound) if k in wheels else 0
    changes.append(wheels_text(wheels) if not wheels else L("4 pneus neufs", "four new tyres") if len(wheels) == 4
                   else L(f"pneus neufs : {wheels_text(wheels)}", f"new tyres: {wheels_text(wheels)}"))
    menu, changes = _plan_damage(menu, changes, repair)
    return menu, changes


class PitCrew:
    """Règle le menu des stands au moment du « box » (mode Auto) ou à la demande."""

    def __init__(self, cfg: dict, demo: bool = False) -> None:
        self.cfg = cfg
        self.demo = demo
        self.mode = cfg.get("pit_auto", "auto")   # "auto" / "demande" / "off"
        self.done_for = None                        # n° d'arrêt déjà préparé
        self.no_fuel_for = None                     # n° d'arrêt pour lequel le pilote a dit « pas d'essence »
        self.tyres_for = None                       # (n° d'arrêt, roues) : « change juste les deux avant »
        self.status = ""                            # pour le tableau de bord
        self.busy = False
        self.say = None
        self.dumped = False                         # liste des lignes du menu déjà écrite dans le journal

    def _dump(self) -> None:
        """Écrit une fois dans le journal toutes les lignes du menu des stands (pour préparer le choix pneu par pneu)."""
        try:
            for it in read_menu():
                opts = [x.get("text", "") for x in it.get("settings", [])]
                print(f"  Menu stand [{it.get('PMC Value')}] {it.get('name')} : {len(opts)} choix, ex. {opts[:4]}")
        except Exception as e:
            print(f"  Menu stand : lecture impossible ({e.__class__.__name__})")

    def update(self, s, p) -> None:
        if not self.dumped and s.on_track and not self.demo:
            self.dumped = True
            threading.Thread(target=self._dump, daemon=True).start()
        if self.mode != "auto" or not s.on_track or s.in_pits or s.session != "course" or s.game_phase == 8:
            return
        if p.ready and p.stops_needed and p.laps_until_box is not None and p.laps_until_box <= 1:
            if self.done_for != s.pit_stops:
                self.prepare(s, p)

    def prepare(self, s, p, asked: bool = False) -> None:
        if self.busy:
            return
        if not p or p.fuel_to_add is None and not asked:
            return
        self.done_for = s.pit_stops
        fuel_total = 0.0 if self.no_fuel_for == s.pit_stops else getattr(p, "fuel_total", None)
        tyres = "Wet" if p.tyre_compound == "pluie" else "dry" if p.tyre_compound == "slicks" else \
            "same" if p.change_tyres else "keep" if p.change_tyres is False else None
        if self.tyres_for and self.tyres_for[0] == s.pit_stops and not p.tyre_compound:
            tyres = tuple(self.tyres_for[1])   # l'ordre du pilote passe avant le calcul
        self.busy = True
        threading.Thread(target=self._run, args=(fuel_total, tyres, s.compound,
                                                       ("all" if getattr(p, "repair_all", False) else "body") if getattr(p, "repair", False)
                                                       else False if getattr(p, "no_repair", False) else None),
                         daemon=True).start()

    def _run(self, fuel_total, tyres, compound, repair) -> None:
        try:
            if self.demo:
                time.sleep(0.5)
                txt = ", ".join(x for x in [L(f"essence à {fuel_total:.0f} litres", f"fuel to {fuel_total:.0f} litres") if fuel_total
                                            else L("pas d'essence", "no fuel") if fuel_total == 0 else "",
                                            {"keep": L("on garde les pneus", "keep the tyres"), "same": L("pneus neufs", "new tyres"),
                                             "Wet": L("pneus pluie", "wet tyres"), "dry": L("pneus slicks", "slick tyres")}.get(tyres, ""),
                                            (L("on répare tout", "full repairs") if repair == "all" else L("réparation de la carrosserie", "bodywork repairs")) if repair
                                            else L("pas de réparation", "no repairs") if repair is False else ""] if x)
                self.status = L(f"✓ Réglé (démo) : {txt}", f"✓ Set (demo): {txt}")
                self._say(L(f"Stand réglé : {txt}.", f"Pit menu set: {txt}."))
                return
            menu = read_menu()
            if not menu:
                raise RuntimeError("menu des stands vide")
            new, changes = plan_menu(menu, fuel_total, tyres, compound, repair)
            status, _ = _req("POST", "/rest/garage/PitMenu/loadPitMenu", new)
            time.sleep(0.4)
            check = read_menu()
            bad = [it["name"] for it in new
                   if (c := _item(check, it["PMC Value"])) and c["currentSetting"] != it["currentSetting"]
                   and it["PMC Value"] in (FUEL, TIRES, DAMAGE) + WHEELS]
            if bad:
                self.status = L("⚠ Menu non pris en compte : ", "⚠ Menu not applied: ") + ", ".join(bad)
                self._say(L("Attention, je n'ai pas réussi à régler tout le menu des stands, vérifie-le.",
                            "Careful, I couldn't set the whole pit menu, check it."))
                print(f"  Menu stand : écart après écriture sur {bad} (statut {status})")
            else:
                self.status = L("✓ Réglé : ", "✓ Set: ") + ", ".join(changes)
                self._say(L("Stand réglé : ", "Pit menu set: ") + ", ".join(changes) + ".")
                print(f"  Menu stand réglé : {changes}")
        except Exception as e:
            self.status = L(f"⚠ Impossible de régler le menu ({e.__class__.__name__})", f"⚠ Couldn't set the menu ({e.__class__.__name__})")
            print(f"  Menu stand : erreur {e!r}")
            self._say(L("Je n'arrive pas à régler le menu des stands, fais-le à la main cette fois.",
                        "I can't set the pit menu, do it manually this time."))
        finally:
            self.busy = False

    def _say(self, text: str) -> None:
        if self.say:
            self.say(None, text, urgent=True)
