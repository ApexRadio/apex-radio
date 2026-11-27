"""
Ingénieur de course pour Le Mans Ultimate — étape 1 : tableau de bord stratégie.

Lancement :
    python app.py          -> lit le jeu en direct
    python app.py --demo   -> course simulée pour tester sans le jeu

Le tableau de bord s'ouvre dans le navigateur (http://localhost:8765).
On peut aussi l'ouvrir sur un téléphone ou une tablette du même réseau
avec l'adresse affichée au démarrage.
"""

from __future__ import annotations

import argparse
import os
import json
import socket
import sys
import threading
import shutil
import time
import traceback
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from strategy import Engineer
from telemetry import DemoSource, Snapshot
import voice as voices
from voice import Voice
import questions
import i18n
import updates
import desktop
from i18n import L
from questions import answer
from laptimes import LapTimes
from trackmap import TrackMap
from behavior import Behavior
from setups import Workshop
from incidents import Incidents
from lmu_probe import Probe
import phrases
import lmukeys
from reflap import RefLap
import annonces
from alerts import Spotter, Traffic, GapTrend, TrackLimits, Damage, Weather, WarmUp, CarInfo, Places, Morale, car_label, set_encourage, PitLane
import debrief
from pitmenu import PitCrew
from radio import save_config
from radio import Radio
from tactics import Penalties, Undercut, Pace, FuelBook

HERE = Path(__file__).parent
from paths import DATA, LOCAL, MIGRATED  # noqa: E402
PORT = 8765


def system_lang() -> str:
    """Premier lancement : français si Windows est en français, sinon anglais."""
    try:
        if sys.platform == "win32":
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "fr" if (lid & 0x3FF) == 0x0C else "en"
        import locale
        return "fr" if (locale.getlocale()[0] or "").lower().startswith("fr") else "en"
    except Exception:
        return "fr"


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.payload = b"{}"
        self.snap = Snapshot()
        self.plan = None
        self.eng = None
        self.map = TrackMap()
        self.radio = Radio(self.on_question, self.on_shortcut)
        import share
        share.CFG = self.radio.cfg      # webhook de l'équipe (⚙️ Discord)
        i18n.set_lang(self.radio.cfg.get("lang") or system_lang())   # avant la voix : elle charge le modèle de la bonne langue
        voices.CHOICE.update(self.radio.cfg.get("voices") or {})      # voix choisie pour chaque langue
        self.voice = Voice()
        self.radio.on_press = self.voice.hush
        self.workshop = None
        self.beh = None
        self.demo = False
        self.last_track = ""
        self.fuel = FuelBook()

    def track(self) -> str:
        return self.snap.track or self.last_track

    # ------------------------------------------------ boutons du tableau de bord et raccourcis du volant
    def toggle_voice(self) -> None:
        v = self.voice
        v.enabled = not v.enabled
        if v.enabled:
            v.say(L("Radio active.", "Radio on."), urgent=True)
        print(f"  Radio : {'activée' if v.enabled else 'coupée'}")

    def toggle_quiet(self) -> None:
        v = self.voice
        v.quiet = not v.quiet
        v.say(L("Mode silence : je ne te dis plus que l'urgent.", "Quiet mode: urgent calls only.") if v.quiet
              else L("Fin du silence, je te redonne toutes les infos.", "Quiet mode off, back to full info."),
              urgent=True)

    def toggle_spotter(self) -> None:
        sp = getattr(self, "spotter", None)
        if sp:
            sp.enabled = not sp.enabled
            self.radio.cfg["spotter"] = sp.enabled
            save_config(self.radio.cfg)
            self.voice.say(L("Spotter activé.", "Spotter on.") if sp.enabled else L("Spotter coupé.", "Spotter off."),
                           urgent=True)

    def on_shortcut(self, name: str) -> None:
        {"spotter": self.toggle_spotter, "radio": self.toggle_voice, "quiet": self.toggle_quiet}[name]()

    def on_question(self, text: str) -> None:
        from strategy import Plan
        raw = answer(text, self.snap, self.plan or Plan())
        import time as _t
        lost = any(k in raw for k in ("pas compris", "Pas sûr d'avoir compris", "didn't get", "Not sure I got",
                                      "rien entendu", "didn't hear anything"))
        if lost and _t.monotonic() - getattr(self.voice, "cut_at", -99) < 20:
            # tu as appuyé pour la faire taire, pas pour lui parler : pas de « je n'ai pas compris »
            print(f"  [ingé] (radio coupée par le pilote, « {text} » ignoré)")
            return
        reply = phrases.dress(raw, answer=True)
        if self.eng is not None:
            self.eng.radio.appendleft({"t": self.snap.elapsed, "text": f"Toi : {text}", "urgent": False, "me": True})
            self.eng.radio.appendleft({"t": self.snap.elapsed, "text": reply, "urgent": False})
        print(f"  [ingé] {reply}")
        self.voice.say(reply, urgent=True)


def make_source(demo: bool):
    if demo:
        return DemoSource()
    if sys.platform != "win32":
        print("La lecture en direct de LMU ne fonctionne que sous Windows. Lance avec --demo pour tester.")
        sys.exit(1)
    from telemetry import AutoSource
    return AutoSource()     # Le Mans Ultimate ou Assetto Corsa EVO, selon le jeu lancé


def loop(state: State, demo: bool) -> None:
    source = make_source(demo)
    eng = Engineer()
    eng.on_say = state.voice.say
    eng.map = state.map   # pour dire où lever le pied quand il faut économiser
    state.eng = eng
    questions.VOICE, questions.ENG = state.voice, eng
    lt = LapTimes()
    questions.LAPTIMES = lt
    beh = Behavior(state.map)
    lt.beh = beh   # pour dire dans quel virage le tour a été invalidé
    beh.say = lambda key, text, **kw: eng.say(key, text, elapsed=state.snap.elapsed)
    questions.BEHAVIOR = beh
    reflap = RefLap(beh)
    questions.REFLAP = reflap
    import relais
    relay = relais.Relay()
    relay.eng = eng   # pneus neufs au changement de pilote
    from equipier import TeamWatch
    team = TeamWatch()
    state.relay = relay
    state.beh = beh
    probe = Probe() if not demo else None
    say = lambda key, text, urgent=False: eng.say(key, text, urgent=urgent, elapsed=state.snap.elapsed)
    spotter = Spotter(state.voice)
    spotter.enabled = state.radio.cfg.get("spotter", True)
    state.spotter = spotter
    traffic, trend, limits, damage = Traffic(beh), GapTrend(), TrackLimits(beh), Damage()
    pitlane = PitLane()
    warmup, carinfo, places, morale = WarmUp(), CarInfo(), Places(), Morale()
    set_encourage(state.radio.cfg.get("encourage", "normal"))
    annonces.load(state.radio.cfg.get("annonces"))
    import behavior as _bh
    _bh.set_coach(state.radio.cfg.get("coaching", True))
    _bh.set_coach_race(state.radio.cfg.get("coach_race", True))
    phrases.set_tone(state.radio.cfg.get("tone", "radio"))
    phrases.set_driver(state.radio.cfg.get("driver_name", ""))
    weather = Weather(demo)
    recorder = debrief.Recorder()
    session_end = {"key": None, "prompt": 0}
    crew = PitCrew(state.radio.cfg, demo)
    crew.say = say
    state.crew = crew
    pen, under, pace = Penalties(), Undercut(), Pace()
    state.pace = pace
    questions.PIT_ACTION = lambda: crew.prepare(state.snap, state.plan, asked=True)

    def set_repair(want: bool, full: bool = True) -> bool:
        """Le pilote dit « répare » / « pas de réparation » : prioritaire jusqu'au prochain arrêt."""
        damage.choice, damage.choice_all = want, full
        for o in (state.snap, state.plan):
            if o is not None:
                o.repair, o.no_repair, o.repair_all = want, not want, want and full
        return apply_now()

    questions.REPAIR_SET = set_repair

    def setup_summary(sn) -> str | None:
        """Fin de session : on annonce exactement ce que l'atelier propose (pas des conseils qu'il ne peut pas appliquer)."""
        try:
            ws, tr = state.workshop, sn.track
            if not ws.state(tr).get("current"):
                return None
            prop = ws.propose(tr, state.beh.issues, state.beh.tyre_findings, state.beh.live_controls(tr),
                              state.fuel.suggest(tr), state.beh.brake_peaks)
        except Exception:
            return None
        if prop.get("error"):
            return None
        bal = [c for c in prop["changes"] if not c.get("fuel") and not c.get("live")]
        if bal:
            items = [i18n.L(f"{c['label']} de {c['from_disp']} à {c['to_disp']}, pour {c['why']}",
                       f"{c['label']} from {c['from_disp']} to {c['to_disp']}, for {c['why']}") for c in bal[:3]]
            return (i18n.L("Pour le setup, je te propose : ", "For the setup, I suggest: ") + " ; ".join(items)
                    + i18n.L(". C'est coché dans l'atelier setup : clique sur Créer, puis recharge le setup au garage.",
                        ". It's ticked in the setup workshop: click Create, then reload the setup in the garage."))
        if state.beh.issues:
            return i18n.L("J'ai noté des choses à améliorer, mais les réglages qui les corrigent sont déjà au bout de leur plage sur ce setup. "
                     "Rien de nouveau à changer pour l'instant.",
                     "I noted things to improve, but the settings that fix them are already at the end of their range on this setup. "
                     "Nothing new to change for now.")
        return None

    def apply_now() -> bool:
        """Ordre du pilote pour le prochain arrêt : on règle le menu des stands tout de suite (sans attendre l'approche
        de l'arrêt), sans marquer l'arrêt comme préparé : la préparation automatique pourra encore ajuster l'essence."""
        sn = state.snap
        if sn is None or not sn.on_track or sn.in_pits or crew.mode == "off" or crew.busy:
            return False
        crew.prepare(sn, state.plan, asked=True, mark_done=crew.done_for == sn.pit_stops)
        return True

    def set_no_fuel() -> bool:
        """Le pilote dit « pas d'essence » / « sans ravitaillement » : valable pour le prochain arrêt."""
        crew.no_fuel_for = state.snap.pit_stops if state.snap is not None else None
        return apply_now()

    questions.FUEL_SET = set_no_fuel

    def set_tyres(wheels: tuple) -> bool:
        """Le pilote dit « change juste les deux avant » / « garde les pneus » : valable pour le prochain arrêt."""
        order = (state.snap.pit_stops, tuple(wheels)) if state.snap is not None else None
        crew.tyres_for = eng.tyre_order = order
        return apply_now()

    questions.TYRES_SET = set_tyres

    def set_amount(litres, energy) -> bool:
        """« énergie à 100 % » / « fais le plein » / « mets 40 litres » : valable pour le prochain arrêt."""
        crew.amount_for = eng.amount_order = (state.snap.pit_stops, litres, energy) if state.snap is not None else None
        crew.no_fuel_for = None
        return apply_now()

    questions.AMOUNT_SET = set_amount

    def set_compound(kind: str) -> bool:
        """« mets les pneus pluie » / « sors les slicks » : valable pour le prochain arrêt."""
        crew.compound_for = eng.compound_order = (state.snap.pit_stops, kind) if state.snap is not None else None
        return apply_now()

    questions.COMPOUND_SET = set_compound

    def cancel_orders(what: str = "tout") -> bool:
        """Le pilote dit « annule » : on oublie ses ordres pour le prochain arrêt, Apex reprend son propre plan."""
        if what in ("tout", "pneus"):
            crew.tyres_for = eng.tyre_order = None
            crew.compound_for = eng.compound_order = None
        if what in ("tout", "essence"):
            crew.no_fuel_for = None
            crew.amount_for = eng.amount_order = None
        if what == "tout":
            damage.choice, damage.choice_all = None, True
            if state.snap is not None:
                damage._apply(state.snap)
                if state.plan is not None:
                    state.plan.repair, state.plan.no_repair, state.plan.repair_all = state.snap.repair, state.snap.no_repair, state.snap.repair_all
        return apply_now()

    questions.CANCEL_SET = cancel_orders
    questions.RACE_FUEL = lambda: state.fuel.brief(state.snap) if state.snap else None
    questions.BRIEFING = lambda: state.fuel.briefing(state.snap) if state.snap else None
    state.fuel.weather = lambda s: questions._forecast_text(Weather.LAST.forecast if Weather.LAST else [], 0.0,
                                                            s.time_left, i18n.L("Météo", "Weather"))

    def setup_sync():
        """Toutes les 15 s : quel setup est chargé dans LMU ? (sélection automatique dans l'atelier)"""
        while not demo:
            try:
                if state.snap.connected and state.snap.track:
                    f = state.workshop.sync_active(state.snap.track)
                    if f:   # un autre setup a remplacé celui qu'on analysait
                        beh.reset_analysis()
                    check_setup_class()
            except Exception:
                traceback.print_exc()
            time.sleep(15)

    warned_setup = set()

    def check_setup_class():
        """Le setup chargé a-t-il été fait pour cette version de la voiture (LMP2 / LMP2 ELMS…) ?"""
        ws, sn = state.workshop, state.snap
        ws.car_class, ws.car = sn.car_class, sn.car
        m = ws.class_mismatch(sn.track)
        ws.mismatch = m
        if not m:
            return
        k = (sn.track, m["file"], m["car"])
        if k in warned_setup:
            return
        warned_setup.add(k)
        if {m["setup"], m["car"]} <= {"LMP2", "LMP2_ELMS"}:
            say(None, i18n.L(
                f"Ton setup {m['file'][:-4]} est fait pour la {car_label(m['setup'])}, et tu es en {car_label(m['car'], sn.car)}. "
                "Pas de souci : c'est la même voiture, je convertirai la copie APEX pour ta version.",
                f"Your setup {m['file'][:-4]} is made for the {car_label(m['setup'])}, and you're in the {car_label(m['car'], sn.car)}. "
                "No problem: it's the same car, I'll convert the APEX copy for your version."), urgent=False)
            return
        say(None, i18n.L(
            f"Attention, ton setup {m['file'][:-4]} a été fait pour la {car_label(m['setup'])}, "
            f"mais tu es en {car_label(m['car'], sn.car)}. Charge plutôt un setup fait pour cette voiture.",
            f"Careful, your setup {m['file'][:-4]} was made for the {car_label(m['setup'])}, "
            f"but you're in the {car_label(m['car'], sn.car)}. Better load a setup made for this car."), urgent=False)

    threading.Thread(target=setup_sync, daemon=True).start()
    inc = Incidents(beh)
    inc.say = lambda key, text, urgent=False: eng.say(key, text, urgent=urgent, elapsed=state.snap.elapsed)
    state.voice.volume = float(state.radio.cfg.get("volume", 1.3))
    if demo:
        demo_dir = make_demo_setups()
        state.workshop = Workshop({**state.radio.cfg, "setups_dir": str(demo_dir), "setup_folder_for": {}})
    else:
        state.workshop = Workshop(state.radio.cfg)
        # dernière voiture connue : l'atelier montre le bon historique (ELMS / WEC) même jeu fermé
        state.workshop.car_class = state.radio.cfg.get("last_car_class", "")
        state.workshop.car = state.radio.cfg.get("last_car", "")
    state.workshop.scan(force=True)
    print(f"  Setups LMU : {state.workshop.dir} ({'trouvé' if state.workshop.ok() else 'introuvable'})")
    if state.workshop.ok():   # touches LMU du joueur, pour les commandes voiture du Stream Deck
        try:
            lmukeys.load(Path(state.workshop.dir).parent.parent)
        except Exception as e:
            print(f"  Touches LMU : lecture impossible ({e.__class__.__name__})")
    last_lap_seen = None

    def fast_loop():
        """Lecture rapide (50 fois/s) de la dynamique pour l'analyse du comportement."""
        k = 0
        n_ok, t_rate = 0, time.monotonic()
        while True:
            try:
                m = source.fast_sample()
                if m:
                    n_ok += 1
                if time.monotonic() - t_rate >= 60:
                    if n_ok:   # diagnostic dans le journal : ~50/s attendu (moins = PC trop chargé)
                        print(f"  Lecture rapide : {n_ok / (time.monotonic() - t_rate):.0f}/s")
                    sn = state.snap
                    if sn.on_track and not sn.in_pits:   # pour vérifier les températures pneus face au jeu
                        r = lambda v: "/".join(f"{x:.0f}" for x in v)
                        print(f"  Pneus °C (AVG/AVD/ARG/ARD) surface {r(sn.tyre_surface_temp)} · couche {r(sn.tyre_inner_temp)}"
                              f" · carcasse {r(sn.tyre_carcass_temp)} · idéal {sn.tyre_opt:.0f} · freins {r(sn.brake_temp)}")
                    n_ok, t_rate = 0, time.monotonic()
                beh.feed(m)
                reflap.feed(m, state.snap, say)
                k += 1
                if k % 2 == 0:
                    spotter.feed(source.spot_sample())
            except Exception:
                traceback.print_exc()
                time.sleep(1)
            time.sleep(0.02)

    threading.Thread(target=fast_loop, daemon=True).start()
    while True:
        try:
            snap = source.read()
            damage.update(snap, say)
            plan = eng.update(snap)
            relay.update(snap, plan, say)
            try:   # mode équipier : voiture d'équipe quand un coéquipier roule
                import telemetry as _tm
                _tm.TEAM_DRIVERS = [x for x in (relay.cfg.get("drivers") or []) if x]
                _tm.TEAM_ON = bool(relay.cfg.get("on"))
                team.update(snap, say)
            except Exception:
                traceback.print_exc()
            lt.update(snap, eng.say)
            state.map.update(snap)
            try:
                team_lap_tick(state)
            except Exception:
                traceback.print_exc()
            spotter.session = snap.session
            inc.update(snap)
            traffic.update(snap, plan, say)
            beh.game = getattr(snap, "game", "lmu")
            if snap.on_track and snap.track:
                bkey = (beh.game, snap.track, snap.car)
                if getattr(beh, "_key", None) not in (None, bkey):
                    beh.new_session()
                beh._key = bkey
            pitlane.update(snap, say)
            trend.update(snap, say)
            limits.update(snap, say)
            warmup.update(snap, say)
            places.update(snap, say)
            morale.update(snap, say)
            carinfo.update(snap, say)
            lmu = getattr(snap, "game", "lmu") == "lmu"   # atelier setup : fichiers LMU seulement
            if state.workshop and lmu and snap.car_class:   # jeu fermé : on garde la dernière voiture (historique ELMS/WEC)
                state.workshop.car_class, state.workshop.car = snap.car_class, snap.car
                if state.radio.cfg.get("last_car_class") != snap.car_class or state.radio.cfg.get("last_car") != snap.car:
                    state.radio.cfg["last_car_class"], state.radio.cfg["last_car"] = snap.car_class, snap.car
                    save_config(state.radio.cfg)
            weather.update(snap, say)
            crew.update(snap, plan)
            pen.update(snap, say)
            under.update(snap, plan, say)
            pace.update(snap, eng, say)
            state.fuel.update(snap, plan, eng, say)
            # fin de session (drapeau à damier) : rappel des réglages garage + ouverture de l'atelier
            key = (snap.track, snap.session_code)
            if snap.on_track and snap.done and session_end["key"] != key and snap.laps_done >= 3:
                session_end["key"] = key
                msg = (setup_summary(snap) if lmu else None) or beh.end_of_session()
                if msg:
                    say(None, msg)
                    if lmu:   # l'atelier setup ne sert qu'à LMU : on ne l'ouvre pas pour AC EVO / iRacing
                        session_end["prompt"] += 1
            recorder.update(snap, lt, beh, eng, state.workshop.state(snap.track).get("label") if snap.track and lmu else None)
            if probe:
                probe.update(snap)
            state.snap, state.plan = snap, plan
            if snap.track:
                state.last_track = snap.track
            if snap.session == "qualif" and lmu:
                state.workshop.set_mode("Qualif")
            elif snap.session == "course" and lmu:
                state.workshop.set_mode("Course")
            L = lt.last
            if L and L.get("lap") != last_lap_seen:
                last_lap_seen = L.get("lap")
                if L.get("valid") and lmu:
                    rv = state.workshop.record_lap(snap.track, L["lap"], beh.issues)
                    if rv:
                        say(None, rv)
            if demo and isinstance(source, DemoSource) and plan.laps_until_box is not None \
                    and plan.laps_until_box <= 1 and snap.lap_frac > 0.6 and not snap.in_pits:
                source.request_pit(plan.fuel_to_add or 0, plan.energy_target, bool(plan.change_tyres or plan.tyre_compound))
            data = {
                "demo": demo,
                "snap": asdict(snap),
                "plan": asdict(plan),
                "radio": list(eng.radio),
                "accent": state.radio.cfg.get("accent", "bleu"),
                "encourage": state.radio.cfg.get("encourage", "normal"),
                "annonces": annonces.CFG,
                "coaching": state.radio.cfg.get("coaching", True),
                "coach_race": state.radio.cfg.get("coach_race", True),
                "tone": state.radio.cfg.get("tone", "radio"),
                "driver_name": state.radio.cfg.get("driver_name", ""),
                "ptt_mode": state.radio.cfg.get("ptt_mode", "hold"),
                "asr": state.radio.cfg.get("asr", "fast"), "asr_loading": bool(getattr(state.radio, "asr_loading", False)),
                "lmu_mode": state.radio.cfg.get("lmu_mode", "ask"),
                "autolaunch_lmu": bool(state.radio.cfg.get("autolaunch_lmu")),
                "game": state.radio.cfg.get("game", "lmu"),
                "voice": {"on": state.voice.enabled, "engine": state.voice.engine, "volume": state.voice.volume,
                          "quiet": state.voice.quiet, "choice": voices.current_id(), "list": voices.catalog(),
                          "name": voices.engineer_name(),
                          "downloading": state.voice.downloading},
                "penalty": pen.ui(snap),
                "phone": PHONE_URL,
                "lang": i18n.LANG,
                "langs": i18n.available(),
                "update": UPD.ui(),
                "share": {"webhook": bool(__import__("share").webhook())},
                "ptt": state.radio.info(),
                "times": lt.ui(snap),
                "map": state.map.info(),
                "behavior": beh.ui(),
                "incidents": inc.active,
                "forecast": weather.ui(snap),
                "spotter": {"on": spotter.enabled, "state": spotter.state},
                "pit": {"mode": crew.mode, "status": crew.status},
                "relay": relay.ui(plan),
                "setup_prompt": session_end["prompt"],
                "ts": time.time(),
            }
        except Exception as e:  # on ne plante jamais pendant une course
            traceback.print_exc()
            data = {"demo": demo, "snap": asdict(Snapshot()), "plan": {}, "radio": [], "error": str(e)}
        with state.lock:
            state.payload = json.dumps(data, default=lambda o: None).encode()
        time.sleep(0.2)


DEMO_SVM = """VehicleClassSetting="Demo Hypercar"
//Setup de démonstration Apex Radio (valeurs fictives)

[GENERAL]
Notes=""
Symmetric=1
FuelSetting=80//90.0L

[FRONTWING]
FWSetting={fw}//{fwd}

[REARWING]
RWSetting={rw}//P{rwd}

[SUSPENSION]
FrontAntiSwaySetting={farb}//{farbd}
RearAntiSwaySetting={rarb}//{rarbd}

[CONTROLS]
RearBrakeSetting={bias}//{biasd}
TractionControlMapSetting={tc}//{tc}

[DRIVELINE]
DiffPowerSetting={dp}//{dpd}
DiffCoastSetting={dc}//{dcd}

""" + "".join(f"""[{w}]
CamberSetting={{cam}}//{{camd}}
PressureSetting={{pr}}//{{prd}}
RideHeightSetting={{rh}}//{{rhd}}

""" for w in ("FRONTLEFT", "FRONTRIGHT", "REARLEFT", "REARRIGHT"))


def make_demo_setups() -> Path:
    """Dossier de setups fictifs pour tester l'atelier en mode démo."""
    d = HERE / "demo_setups" / "Circuit de demo"
    d.mkdir(parents=True, exist_ok=True)
    arb = ["D18 S-S", "D18 S-H", "D18 H-H", "D22 S-S", "D22 S-H", "D22 H-H"]
    diff = ["FF6-60 deg", "FF6-55 deg", "FF6-45 deg", "FF6-30 deg", "FF6-25 deg"]
    for name, k in (("Demo base.svm", 2), ("Demo ancien.svm", 3)):
        f = d / name
        if f.exists():
            continue
        f.write_text(DEMO_SVM.format(
            fw=k, fwd=f"{k} deg", rw=k, rwd=k + 1, farb=k, farbd=arb[k], rarb=k - 1, rarbd=arb[k - 1],
            bias=14 + k, biasd=f"{54.5 - 0.45 * k:.1f}:{45.5 + 0.45 * k:.1f}", tc=3 + k, dp=k, dpd=diff[k], dc=k, dcd=diff[k],
            cam=10 + k, camd=f"{-1.8 + 0.1 * k:.1f} deg", pr=k, prd=f"{130 + 2 * k} kPa", rh=8 + k, rhd=f"{4.0 + 0.1 * k:.1f} cm"),
            encoding="utf-8")
    return d.parent


def make_handler(state: State):
    html = (HERE / "ui" / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/mics") or self.path.startswith("/api/map") or self.path.startswith("/api/traductions"):
                data = state.radio.mics() if self.path.startswith("/api/mics") else i18n.catalog() \
                    if self.path.startswith("/api/traductions") else {**state.map.info(), "points": state.map.points()}
                body, ctype = json.dumps(data).encode(), "application/json"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/debrief") or self.path.rstrip("/") in ("/records", "/relais"):
                if self.path.rstrip("/") == "/relais":
                    import relais
                    body = relais.page().encode()
                elif self.path.rstrip("/") == "/records":
                    body = debrief.records_page().encode()
                elif self.path.rstrip("/") == "/debriefs":
                    body = debrief.index_page().encode()
                else:
                    name = self.path.split("/")[-1]
                    f = debrief.DIR / f"{name}.json"
                    if not name.replace("_", "").replace("-", "").isalnum() or not f.exists():
                        self.send_error(404)
                        return
                    # rendu à la demande : la page suit la langue choisie
                    body = debrief.render(json.loads(f.read_text(encoding="utf-8"))).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/api/setup"):
                ws, beh = state.workshop, state.beh
                if ws is None:
                    data = {"ok": False}
                else:
                    tr = state.track()
                    fuel = state.fuel.suggest(tr)
                    data = {**ws.propose(tr, beh.issues, beh.tyre_findings, beh.live_controls(tr), fuel, beh.brake_peaks),
                            "folders": ws.folders(), "analysis_laps": beh.laps_seen, "fuel": fuel}
                body = json.dumps(data, default=lambda o: None).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/api/relais"):
                rl = getattr(state, "relay", None)
                import relais
                if rl:
                    data = rl.info(state.plan, state.snap)
                else:
                    c = relais.load()
                    fm, src = relais.tank_minutes(c, None, state.snap)
                    data = {"cfg": c, "plan": relais.plan(c, fm), "fuel_stint_min": fm, "fuel_src": src, "live": None,
                            "races": relais.races()}
                try:
                    data["team"] = live_team(state)
                except Exception:
                    data["team"] = None
                body, ctype = json.dumps(data, default=lambda o: None).encode(), "application/json"
            elif self.path.startswith("/api/sd"):
                # état résumé pour le plugin Stream Deck (léger, interrogé chaque seconde)
                body, ctype = json.dumps(sd_state(state), default=lambda o: None).encode(), "application/json"
            elif self.path.startswith("/api/state"):
                with state.lock:
                    body = state.payload
                ctype = "application/json"
            elif self.path.startswith("/api/ping"):         # « c'est bien Apex Radio sur ce port ? »
                body, ctype = json.dumps({"app": "apex-radio", "version": UPD.version}).encode(), "application/json"
            elif self.path.startswith("/api/phone"):         # adresse de la vue téléphone (pour le QR code)
                body, ctype = json.dumps({"url": PHONE_URL}).encode(), "application/json"
            elif self.path.split("?")[0] == "/qrcode.js":       # QR code de la vue téléphone (MIT, Kazuhiko Arase)
                body, ctype = (HERE / "ui" / "qrcode.js").read_bytes(), "text/javascript; charset=utf-8"
            elif self.path.split("?")[0] == "/fsel.js":          # menus déroulants visibles dans les vidéos
                body, ctype = (HERE / "ui" / "fsel.js").read_bytes(), "text/javascript; charset=utf-8"
            elif self.path == "/favicon.ico":
                body, ctype = (HERE / "apex.ico").read_bytes(), "image/x-icon"
            elif self.path.split("?")[0].rstrip("/") == "/compare":     # comparer deux tours (courbes + carte)
                body, ctype = (HERE / "ui" / "compare.html").read_bytes(), "text/html; charset=utf-8"
            elif self.path.split("?")[0].startswith("/api/laps"):
                import compare
                name = self.path.split("?")[0][len("/api/laps"):].strip("/")
                data = compare.get(name) if name else compare.listing()
                if data is None:
                    self.send_error(404)
                    return
                body, ctype = json.dumps(data).encode(), "application/json"
            elif self.path.split("?")[0].rstrip("/") == "/overlay":   # overlay OBS pour les streamers (fond transparent)
                body, ctype = (HERE / "ui" / "overlay.html").read_bytes(), "text/html; charset=utf-8"
            elif self.path.rstrip("/") in ("/tel", "/phone"):
                body, ctype = (HERE / "ui" / "tel.html").read_bytes(), "text/html; charset=utf-8"
            elif self.path in ("/", "/index.html"):
                # relu à chaque fois : une mise à jour du tableau de bord s'affiche sans relancer l'appli
                body, ctype = (HERE / "ui" / "index.html").read_bytes(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            v = state.voice
            if self.path == "/api/voice/toggle":
                state.toggle_voice()
            elif self.path in ("/api/ptt/down", "/api/ptt/up"):
                state.radio.ext_ptt(self.path.endswith("down"))
            elif self.path == "/api/voice/repeat":
                last = getattr(v, "last_text", "")
                v.say(last or L("Rien à répéter pour l'instant.", "Nothing to repeat yet."), urgent=True)
            elif self.path == "/api/lang":
                n = int(self.headers.get("Content-Length") or 0)
                lang = json.loads(self.rfile.read(n) or b"{}").get("lang", "fr")
                i18n.set_lang(lang)
                state.radio.cfg["lang"] = i18n.LANG
                save_config(state.radio.cfg)
                v.flush()
                v.say(L("Radio en français.", "Radio in English."))
            elif self.path == "/api/voice/quiet":
                state.toggle_quiet()
            elif self.path == "/api/relais/export":
                import relais
                n = int(self.headers.get("Content-Length") or 0)
                body = json.dumps(relais.race_export(json.loads(self.rfile.read(n) or b"{}"))).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path in ("/api/laps/export", "/api/laps/import"):
                import compare
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                if self.path.endswith("export"):
                    drv = state.radio.cfg.get("driver_name") or getattr(state.snap, "driver", "") or ""
                    res = compare.export(str(req.get("id") or ""), str(req.get("k") or ""), drv)
                else:
                    res = compare.import_lap(req.get("lap") or {})
                body = json.dumps(res).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/api/setup/race":
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                state.fuel.set_race(state.track(), req.get("minutes"), req.get("laps"))
            elif self.path == "/api/pit/mode":
                n = int(self.headers.get("Content-Length") or 0)
                mode = json.loads(self.rfile.read(n) or b"{}").get("mode")
                crew = getattr(state, "crew", None)
                if crew and mode in ("auto", "demande", "off"):
                    crew.mode = mode
                    state.radio.cfg["pit_auto"] = mode
                    save_config(state.radio.cfg)
            elif self.path == "/api/pit/now":
                crew = getattr(state, "crew", None)
                if crew:
                    crew.prepare(state.snap, state.plan, asked=True)
            elif self.path == "/api/spotter/toggle":
                state.toggle_spotter()
            elif self.path == "/api/show":
                desktop.open_window(f"http://localhost:{PORT}")
            elif self.path == "/api/update/install":
                ok = UPD.install()
                self.send_response(204 if ok else 409)
                self.end_headers()
                return
            elif self.path == "/api/quit":
                self.send_response(204)
                self.end_headers()
                print("  Arrêt demandé depuis le tableau de bord.")
                threading.Timer(0.3, lambda: os._exit(0)).start()
                return
            elif self.path == "/api/voice/volume":
                n = int(self.headers.get("Content-Length") or 0)
                vol = float(json.loads(self.rfile.read(n) or b"{}").get("v", 1.3))
                v.volume = max(0.6, min(1.6, vol))
                state.radio.cfg["volume"] = v.volume
                save_config(state.radio.cfg)
                v.say(L("Radio check, niveau du son.", "Radio check, volume level."))
            elif self.path == "/api/ptt/learn":
                n = int(self.headers.get("Content-Length") or 0)
                target = (json.loads(self.rfile.read(n) or b"{}") if n else {}).get("target", "ptt")
                state.radio.start_learning(target)
            elif self.path in ("/api/lmu/key", "/api/lmu/chat"):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                ok = lmukeys.press(str(body.get("cmd", ""))) if self.path.endswith("key") else lmukeys.chat(str(body.get("text", "")))
                if not ok:
                    self.send_response(409)
                    self.end_headers()
                    return
            elif self.path == "/api/lmu/launch":
                launch_lmu(state.radio.cfg.get("lmu_mode", "ask"), state.radio.cfg.get("game", "lmu"))
            elif self.path == "/api/game":
                n = int(self.headers.get("Content-Length") or 0)
                g = json.loads(self.rfile.read(n) or b"{}").get("game", "lmu")
                state.radio.cfg["game"] = g if g in GAME_NAMES else "lmu"
                save_config(state.radio.cfg)
            elif self.path == "/api/lmu/mode":
                n = int(self.headers.get("Content-Length") or 0)
                m = json.loads(self.rfile.read(n) or b"{}").get("mode", "ask")
                state.radio.cfg["lmu_mode"] = m if m in ("ask", "normal", "vr", "openxr") else "ask"
                save_config(state.radio.cfg)
            elif self.path == "/api/lmu/autolaunch":
                n = int(self.headers.get("Content-Length") or 0)
                state.radio.cfg["autolaunch_lmu"] = bool(json.loads(self.rfile.read(n) or b"{}").get("on"))
                save_config(state.radio.cfg)
            elif self.path == "/api/asr":
                n = int(self.headers.get("Content-Length") or 0)
                state.radio.set_asr(json.loads(self.rfile.read(n) or b"{}").get("mode", "fast"))
            elif self.path == "/api/pttmode":
                n = int(self.headers.get("Content-Length") or 0)
                m = json.loads(self.rfile.read(n) or b"{}").get("mode", "hold")
                state.radio.cfg["ptt_mode"] = "toggle" if m == "toggle" else "hold"
                save_config(state.radio.cfg)
            elif self.path == "/api/relais":
                n = int(self.headers.get("Content-Length") or 0)
                cfg = json.loads(self.rfile.read(n) or b"{}")
                rl = getattr(state, "relay", None)
                import relais
                act = cfg.pop("_race", None)
                bad = False
                if act == "import":
                    got = relais.race_import(cfg.get("race"))
                    bad = got is None
                    cfg = got or (rl.cfg if rl else relais.load())
                elif act == "store":
                    relais.race_store(cfg)          # garde la course… et elle reste la course active
                elif act == "load":
                    cfg = relais.race_get(str(cfg.get("key", ""))) or (rl.cfg if rl else relais.load())
                elif act == "drop":
                    relais.race_drop(str(cfg.get("key", "")))
                    cfg = rl.cfg if rl else relais.load()
                if rl:
                    rl.reload(cfg)
                    data = rl.info(state.plan, state.snap)
                else:
                    c = relais.save(cfg)
                    fm, src = relais.tank_minutes(c, None, state.snap)
                    data = {"cfg": c, "plan": relais.plan(c, fm), "fuel_stint_min": fm, "fuel_src": src, "live": None,
                            "races": relais.races()}
                if bad:
                    data["error"] = "format"
                body = json.dumps(data, default=lambda o: None).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/api/coaching":
                n = int(self.headers.get("Content-Length") or 0)
                on = bool(json.loads(self.rfile.read(n) or b"{}").get("on", True))
                state.radio.cfg["coaching"] = on
                save_config(state.radio.cfg)
                import behavior as _bh
                _bh.set_coach(on)
            elif self.path == "/api/coach_race":
                n = int(self.headers.get("Content-Length") or 0)
                on = bool(json.loads(self.rfile.read(n) or b"{}").get("on", True))
                state.radio.cfg["coach_race"] = on
                save_config(state.radio.cfg)
                import behavior as _bh
                _bh.set_coach_race(on)
            elif self.path == "/api/annonces":
                n = int(self.headers.get("Content-Length") or 0)
                state.radio.cfg["annonces"] = annonces.load(json.loads(self.rfile.read(n) or b"{}"))
                save_config(state.radio.cfg)
            elif self.path == "/api/encourage":
                n = int(self.headers.get("Content-Length") or 0)
                lv = json.loads(self.rfile.read(n) or b"{}").get("level", "normal")
                if lv in ("discret", "normal", "motivant"):
                    state.radio.cfg["encourage"] = lv
                    save_config(state.radio.cfg)
                    set_encourage(lv)
            elif self.path == "/api/tone":
                n = int(self.headers.get("Content-Length") or 0)
                tn = json.loads(self.rfile.read(n) or b"{}").get("tone", "radio")
                if tn in phrases.TONES:
                    state.radio.cfg["tone"] = tn
                    save_config(state.radio.cfg)
                    phrases.set_tone(tn)
            elif self.path in ("/api/setup/dir", "/api/setup/pickdir"):
                n = int(self.headers.get("Content-Length") or 0)
                want = (json.loads(self.rfile.read(n) or b"{}").get("dir") or "").strip().strip('"')
                if self.path == "/api/setup/pickdir":
                    want = pick_folder() or ""
                res = set_setups_dir(state, want) if want else {"ok": False, "cancel": True}
                body = json.dumps(res).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
                return
            elif self.path == "/api/driver":
                n = int(self.headers.get("Content-Length") or 0)
                nm = str(json.loads(self.rfile.read(n) or b"{}").get("name", "")).strip()[:24]
                state.radio.cfg["driver_name"] = nm
                save_config(state.radio.cfg)
                phrases.set_driver(nm)
                if nm:
                    v.say(L(f"Bien reçu, {nm}.", f"Copy that, {nm}."))
            elif self.path.startswith("/api/share/"):
                import share
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                what = self.path.rsplit("/", 1)[-1]
                out = {"ok": False}
                if what == "open":
                    out = {"ok": share.open_discord(str(req.get("kind", "")), str(req.get("game", "lmu")))}
                elif what == "webhook":            # enregistrer (et tester) le webhook de l'équipe
                    ok = share.set_webhook(req.get("url", ""))
                    out = {"ok": ok, "set": bool(share.webhook())}
                    if ok and share.webhook() and req.get("test"):
                        sent, why = share.post(L("✅ Apex Radio est relié à ce salon : les chronos, setups et débriefs "
                                                 "partagés par l'équipe arriveront ici.",
                                                 "✅ Apex Radio is linked to this channel: the team's shared lap times, setups "
                                                 "and debriefs will arrive here."))
                        out = {"ok": sent, "set": True, "why": why}
                elif what == "text":               # message de chronos / débrief : vers l'équipe
                    sent, why = share.post(str(req.get("text", ""))[:1900])
                    out = {"ok": sent, "why": why}
                elif what == "setup":              # fichier setup : presse-papiers, ou équipe
                    f, text = share.setup_file(state.workshop, state.track())
                    if not f:
                        out = {"ok": False, "why": "no-file"}
                    elif req.get("team"):
                        sent, why = share.post(text, f)
                        out = {"ok": sent, "why": why, "file": f.name}
                    else:
                        out = {"ok": share.copy_file(f), "file": f.name, "text": text}
                        share.open_discord("setups", "lmu")
                body = json.dumps(out).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
                return
            elif self.path == "/api/journal":
                body = json.dumps(send_journal()).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
                return
            elif self.path == "/api/accent":
                n = int(self.headers.get("Content-Length") or 0)
                a = json.loads(self.rfile.read(n) or b"{}").get("accent", "bleu")
                if a in ("bleu", "orange", "vert", "rouge", "violet", "jaune", "blanc"):
                    state.radio.cfg["accent"] = a
                    save_config(state.radio.cfg)
            elif self.path == "/api/shortcut/clear":
                n = int(self.headers.get("Content-Length") or 0)
                state.radio.clear_shortcut(json.loads(self.rfile.read(n) or b"{}").get("target", ""))
            elif self.path in ("/api/setup/select", "/api/setup/create", "/api/setup/restore", "/api/setup/mode"):
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                ws, tr = state.workshop, state.track()
                if req.get("mode"):
                    ws.set_mode(req["mode"])
                if self.path.endswith("mode"):
                    out = {"error": None}
                elif self.path.endswith("restore"):
                    out = ws.restore(tr, int(req.get("version") or 0))
                    if not out.get("error"):
                        state.beh.reset_analysis()
                        state.eng.say(None, L(f"Setup remis en version {out['version'][1:]}. Recharge-le au garage.",
                                              f"Setup restored to version {out['version'][1:]}. Reload it in the garage."), elapsed=state.snap.elapsed)
                elif self.path.endswith("select"):
                    prev = ws.state(tr)
                    ws.select(tr, req.get("folder"), req.get("file"))
                    if not state.demo:
                        save_config(state.radio.cfg)
                    # tu indiques le setup avec lequel tu viens de rouler : l'analyse le concerne, on la garde.
                    # On ne repart de zéro que si tu remplaces un setup déjà choisi par un autre.
                    if prev.get("current") and (prev.get("folder"), prev.get("current")) != (req.get("folder"), req.get("file")):
                        state.beh.reset_analysis()
                    out = {"error": None}
                else:
                    prop = ws.propose(tr, state.beh.issues, state.beh.tyre_findings, state.beh.live_controls(tr),
                                      state.fuel.suggest(tr), state.beh.brake_peaks)
                    keep = set(req.get("keys") or [])
                    chosen = [c for c in prop["changes"] if f"{c['section']}|{c['key']}" in keep]
                    out = ws.create(tr, chosen)
                    if not out.get("error"):
                        state.beh.reset_analysis()
                        state.eng.say(None, L(f"Setup {ws.mode.lower()} mis à jour, version {out['version'][1:]}. Recharge-le au garage, je refais l'analyse.",
                                              f"{'Qualifying' if ws.mode == 'Qualif' else 'Race'} setup updated, version {out['version'][1:]}. "
                                              "Reload it in the garage, I'll redo the analysis."),
                                      elapsed=state.snap.elapsed)
                body = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/api/mic":
                n = int(self.headers.get("Content-Length") or 0)
                idx = json.loads(self.rfile.read(n) or b"{}").get("index")
                state.radio.set_mic(idx)
            elif self.path == "/api/ask":
                n = int(self.headers.get("Content-Length") or 0)
                q = json.loads(self.rfile.read(n) or b"{}").get("q", "")
                threading.Thread(target=state.on_question, args=(q,), daemon=True).start()
            elif self.path == "/api/voice/choose":
                n = int(self.headers.get("Content-Length") or 0)
                vid = json.loads(self.rfile.read(n) or b"{}").get("id", "")
                if v.choose(vid):
                    state.radio.cfg["voices"] = dict(voices.CHOICE)
                    save_config(state.radio.cfg)
                    name = voices.engineer_name()
                    if all(f.exists() for f in v._files(vid)):
                        v.say(voices.L_ready(name), urgent=True)
                    else:   # l'ancienne voix prévient ; la nouvelle se présentera une fois téléchargée
                        v.say(L(f"Je télécharge la voix de {name}, {'elle' if voices.engineer_female() else 'il'} prend la radio dans une minute.",
                                f"Downloading {name}'s voice, it'll take over the radio in a minute."), urgent=True)
            elif self.path == "/api/voice/test":
                v.say(L("Radio check. Tu m'entends bien ? On est prêts pour la course.", "Radio check. Do you copy? We're ready to race."))
            else:
                self.send_error(404)
                return
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


PHONE_URL = ""
UPD = updates.Updates()


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class ApexServer(ThreadingHTTPServer):
    """Serveur du tableau de bord, en exclusivité sur son port.

    Sous Windows, l'option « réutiliser l'adresse » permet à un 2e Apex Radio d'écouter sur le même port :
    les pages viennent alors au hasard de l'un ou de l'autre. On la remplace par l'accès exclusif."""
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


PORTS = range(8765, 8776)          # 8765, sinon le suivant libre (Pimax Play occupe aussi le 8765)
PORT_FILE = LOCAL / "port.txt"


def _port_busy(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def is_apex(port: int) -> bool:
    """Ce qui répond sur ce port est bien Apex Radio (et pas un autre logiciel, ex. Pimax Play) ?"""
    import urllib.request
    if not _port_busy(port):
        return False
    for path, test in (("/api/ping", lambda d: d.get("app") == "apex-radio"),
                       ("/api/state", lambda d: "snap" in d or "demo" in d)):     # (versions sans /api/ping)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                if test(json.load(r)):
                    return True
        except Exception:
            pass
    return False


def find_running() -> int | None:
    """Port d'un Apex Radio déjà lancé, ou None."""
    try:
        saved = [int(PORT_FILE.read_text().strip())]
    except Exception:
        saved = []
    for port in dict.fromkeys(saved + list(PORTS)):
        if is_apex(port):
            return port
    return None


def live_team(state) -> dict | None:
    """Voiture d'équipe en direct, pour le « mur des stands » de la page Relais : le coéquipier qui roule
    (mode équipier), ou toi si c'est toi qui es en piste en course."""
    s = getattr(state, "snap", None)
    if not s or not s.connected:
        return None
    if s.team:
        t = {**s.team, "me": False}
    elif s.on_track and s.session == "course":
        side = lambda o, g: {"name": (o or {}).get("name"), "gap": g} if o else None
        t = {"me": True, "driver": s.driver, "car": s.car, "place": s.position, "cpos": s.class_position, "class": s.car_class,
             "laps": s.laps_done, "last": s.last_lap, "best": s.best_lap, "pits": s.in_pits, "stops": s.pit_stops,
             "penalties": s.penalties, "time_left": s.time_left, "track": s.track,
             "fuel": round(s.fuel, 1) if s.fuel else None, "energy": round(s.energy * 100) if s.energy else None,
             "ahead": side(s.ahead, s.gap_class_ahead), "behind": side(s.behind, s.gap_class_behind)}
    else:
        return None
    # météo (la même pour tout le monde)
    t["weather"] = {"air": round(s.air_temp), "track": round(s.track_temp), "rain": round((s.raining or 0) * 100),
                    "wet": round((s.wetness or 0) * 100)}
    # voitures sur la carte : la voiture d'équipe, celles devant / derrière dans sa catégorie, et les autres en petit
    names = {"team": t.get("driver"), "ahead": (t.get("ahead") or {}).get("name"), "behind": (t.get("behind") or {}).get("name")}
    cars = []
    for c in s.cars or []:
        if t["me"]:                       # c'est toi qui roules : le jeu indique déjà devant / derrière
            role = "team" if c.get("me") else c.get("rel") or ""
            cars.append({"x": round(c.get("x", 0), 1), "z": round(c.get("z", 0), 1), "r": role, "pits": bool(c.get("pits"))})
            continue
        role = "team" if c.get("name") == names["team"] else \
            "ahead" if names["ahead"] and c.get("name") == names["ahead"] else \
            "behind" if names["behind"] and c.get("name") == names["behind"] else ""
        cars.append({"x": round(c.get("x", 0), 1), "z": round(c.get("z", 0), 1), "r": role, "pits": bool(c.get("pits"))})
    t["cars"] = cars
    t["map_version"] = state.map.info().get("version") if getattr(state, "map", None) else None
    t["history"] = state.__dict__.get("team_laps", [])[-30:]
    return t


def team_lap_tick(state) -> None:
    """Note chaque tour bouclé par la voiture d'équipe (toi ou un coéquipier), en continu dès le début de la course,
    même quand la page Relais n'est pas ouverte : c'est le graphique « tours du relais »."""
    s = getattr(state, "snap", None)
    if not s or not s.connected:
        return
    if s.team:
        n, last, drv, pits = s.team.get("laps") or 0, s.team.get("last"), s.team.get("driver") or "", bool(s.team.get("pits"))
    elif s.on_track and s.session == "course":
        n, last, drv, pits = s.laps_done, s.last_lap, s.driver, s.in_pits
    else:
        return
    hist = state.__dict__.setdefault("team_laps", [])
    if hist and n < hist[-1]["n"]:
        hist.clear()                                   # nouvelle course
    if last and n and (not hist or n > hist[-1]["n"]):
        hist.append({"n": n, "t": round(last, 3), "d": drv, "pit": pits or bool(getattr(s, "pit_state", 0))})
        del hist[:-200]


def already_running() -> bool:
    """Un Apex Radio répond déjà (sur 8765 ou sur le port de secours) ?"""
    global PORT
    p = find_running()
    if p:
        PORT = p
    return p is not None


def replace_other_mode(demo: bool) -> bool:
    """Le Apex Radio déjà lancé est dans l'autre mode (démo / course) : on l'arrête pour démarrer celui demandé."""
    import urllib.request
    base = f"http://127.0.0.1:{PORT}"
    try:
        with urllib.request.urlopen(base + "/api/state", timeout=2) as r:
            other_demo = bool(json.load(r).get("demo"))
    except Exception:
        return False
    if other_demo == demo:
        return False
    print("  Un Apex Radio " + ("en course" if not other_demo else "en démo") + " tourne déjà : je l'arrête.")
    try:
        urllib.request.urlopen(urllib.request.Request(base + "/api/quit", data=b"{}", method="POST"), timeout=3).close()
    except Exception:
        pass
    for _ in range(40):
        time.sleep(0.25)
        if not is_apex(PORT):
            return True
    return False


def ensure_packages() -> None:
    """Installe les composants manquants et note le résultat dans journal.txt."""
    import importlib.util
    import subprocess
    needed = {"piper": "piper-tts", "faster_whisper": "faster-whisper", "sounddevice": "sounddevice", "pygame": "pygame-ce"}
    if sys.platform == "win32":
        needed.update({"pystray": "pystray", "PIL": "Pillow", "webview": "pywebview"})
    missing = [pkg for mod, pkg in needed.items() if importlib.util.find_spec(mod) is None]
    if not missing:
        return
    print(f"  Installation des composants manquants : {', '.join(missing)} (quelques minutes)…")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing],
                       capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(r.stdout[-3000:])
    if r.returncode:
        print("  ÉCHEC de l'installation :")
        print(r.stderr[-4000:])
    else:
        print("  Composants installés.")


class _Tee:
    """Écrit à l'écran et dans journal.txt (pour le dépannage)."""
    def __init__(self, stream, f):
        self.stream, self.f = stream, f
    def write(self, data):
        try:
            self.stream.write(data)
        except Exception:
            pass
        self.f.write(data); self.f.flush()
    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass


LMU_STEAM_ID = 2399420
ACEVO_STEAM_ID = 3058630   # Assetto Corsa EVO
AMS2_STEAM_ID = 1066890    # Automobilista 2
GAME_NAMES = {"lmu": "Le Mans Ultimate", "acevo": "Assetto Corsa EVO", "ams2": "Automobilista 2"}


def _steam_exe() -> str | None:
    """Chemin de steam.exe (registre Windows), pour lancer LMU sans passer par le lien steam://."""
    try:
        import winreg
        for root, key, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamExe"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(root, key) as k:
                    v = str(winreg.QueryValueEx(k, name)[0])
                p = Path(v) if v.lower().endswith(".exe") else Path(v) / "steam.exe"
                if p.exists():
                    return str(p)
            except OSError:
                continue
    except Exception:
        pass
    return None


def pick_folder() -> str | None:
    """Fenêtre Windows « Choisir un dossier » (par PowerShell, rien à installer)."""
    if sys.platform != "win32":
        return None
    import subprocess
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          "$o=New-Object System.Windows.Forms.Form;$o.TopMost=$true;"
          "$f=New-Object System.Windows.Forms.FolderBrowserDialog;"
          "$f.Description='Dossier Le Mans Ultimate (ou UserData\\player\\Settings)';"
          "if($f.ShowDialog($o) -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8;$f.SelectedPath}")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, timeout=600,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.decode("utf-8", "ignore").strip() or None
    except Exception:
        return None


def set_setups_dir(state, raw: str) -> dict:
    """Dossier des setups choisi à la main : on accepte aussi le dossier du jeu ou UserData."""
    p = Path(raw)
    for c in (p / "UserData" / "player" / "Settings", p / "player" / "Settings", p / "Settings", p):
        if c.is_dir() and (c.name.lower() == "settings" or any(c.glob("*/*.svm"))):
            state.radio.cfg["setups_dir"] = str(c)
            save_config(state.radio.cfg)
            state.workshop.dir = c
            try:
                state.workshop.scan(force=True)
            except Exception:
                pass
            return {"ok": True, "dir": str(c)}
    return {"ok": False, "error": i18n.L("Ce dossier ne contient pas les setups de LMU.", "This folder doesn't contain LMU setups.")}


# options de lancement de LMU dans Steam (appinfo) : 0 = normal, 2 = « vr » (+VR, SteamVR), 3 = « openxr » (+XR)
LMU_MODES = {"normal": "default", "vr": "vr", "openxr": "openxr"}


def sd_state(state) -> dict:
    """Résumé pour le Stream Deck : place, essence, écarts, box, et l'état des boutons."""
    s, p = getattr(state, "snap", None), getattr(state, "plan", None)
    sp = getattr(state, "spotter", None)
    r = state.radio
    out = {"ok": True, "lang": i18n.LANG, "connected": bool(s and s.connected), "on_track": bool(s and s.on_track),
           "radio": r.state, "voice_on": state.voice.enabled, "quiet": state.voice.quiet,
           "spotter": bool(sp and sp.enabled)}
    if s and s.on_track:
        out.update({"pos": s.class_position or s.position, "cars": s.num_cars, "fuel": round(s.fuel, 1),
                    "fuel_cap": s.fuel_capacity, "energy": s.energy, "gap_ahead": s.gap_class_ahead,
                    "gap_behind": s.gap_class_behind, "last": s.last_lap, "best": s.best_lap,
                    "in_pits": s.in_pits, "car": s.car_state})
    out["keys"] = lmukeys.available()
    if p:
        out.update({"range_laps": p.range_laps, "box_in": p.laps_until_box, "fuel_per_lap": p.fuel_per_lap})
    return out


def launch_lmu(mode: str = "ask", game: str = "lmu") -> bool:
    """Lance Le Mans Ultimate par Steam. mode « ask » : steam.exe -applaunch (Steam propose ses options s'il y en a) ;
    « normal » / « vr » / « openxr » : on demande directement cette option à Steam (steam://launch/<id>/<type>)."""
    if game == "acevo":
        return launch_steam_game(ACEVO_STEAM_ID, "Assetto Corsa EVO")
    if game == "ams2":
        return launch_steam_game(AMS2_STEAM_ID, "Automobilista 2")
    url = f"steam://rungameid/{LMU_STEAM_ID}"
    try:
        if sys.platform == "win32":
            exe = _steam_exe()
            import subprocess
            flags = getattr(subprocess, "DETACHED_PROCESS", 0)
            if mode in LMU_MODES:
                url = f"steam://launch/{LMU_STEAM_ID}/{LMU_MODES[mode]}"
                if exe:
                    subprocess.Popen([exe, url], close_fds=True, creationflags=flags)
                else:
                    os.startfile(url)
            elif exe:
                subprocess.Popen([exe, "-applaunch", str(LMU_STEAM_ID)], close_fds=True, creationflags=flags)
            else:
                os.startfile(url)
        else:
            import webbrowser
            webbrowser.open(url)
        print("  Lancement de Le Mans Ultimate par Steam…")
        return True
    except Exception as e:
        print(f"  Impossible de lancer LMU : {e!r}")
        return False


def launch_steam_game(app_id: int, name: str) -> bool:
    """Lance un jeu Steam (sans option de lancement particulière)."""
    try:
        if sys.platform == "win32":
            exe = _steam_exe()
            import subprocess
            if exe:
                subprocess.Popen([exe, "-applaunch", str(app_id)], close_fds=True,
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            else:
                os.startfile(f"steam://rungameid/{app_id}")
        else:
            import webbrowser
            webbrowser.open(f"steam://rungameid/{app_id}")
        print(f"  Lancement de {name} par Steam…")
        return True
    except Exception as e:
        print(f"  Impossible de lancer {name} : {e!r}")
        return False


def autolaunch_lmu(state) -> None:
    """Option : si LMU n'est pas déjà lancé quelques secondes après l'ouverture d'Apex, on le démarre."""
    time.sleep(6)
    if state.radio.cfg.get("autolaunch_lmu") and not getattr(state.snap, "connected", False):
        launch_lmu(state.radio.cfg.get("lmu_mode", "ask"), state.radio.cfg.get("game", "lmu"))


JOURNAUX = DATA / "journaux"      # copies du journal : une par lancement + celles faites avec le bouton


def _prune_journaux(keep: int = 20) -> None:
    try:
        files = sorted(JOURNAUX.glob("journal Apex *.txt"), key=lambda p: p.stat().st_mtime)
        for p in files[:-keep]:
            p.unlink()
    except OSError:
        pass


def keep_previous_journal() -> None:
    """Au lancement, le journal précédent est gardé dans Documents/Apex Radio/journaux (avant, il était effacé :
    il fallait l'envoyer avant de relancer Apex)."""
    src = LOCAL / "journal.txt"
    try:
        if src.exists() and src.stat().st_size > 200:
            JOURNAUX.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y-%m-%d %Hh%M", time.localtime(src.stat().st_mtime))
            shutil.copyfile(src, JOURNAUX / f"journal Apex {stamp}.txt")
            _prune_journaux()
    except OSError:
        pass


def send_journal() -> dict:
    """Bouton « Copier mon journal » : copie le journal du moment dans Documents/Apex Radio/journaux, le met dans le
    presse-papiers (Ctrl+V dans Discord le colle comme un fichier) et l'affiche dans l'Explorateur."""
    sys.stdout.flush()
    src = LOCAL / "journal.txt"
    try:
        JOURNAUX.mkdir(parents=True, exist_ok=True)
        dst = JOURNAUX / f"journal Apex {time.strftime('%Y-%m-%d %Hh%M')}.txt"
        shutil.copyfile(src, dst)
        _prune_journaux()
    except OSError as e:
        return {"ok": False, "error": e.__class__.__name__}
    clip = False
    if sys.platform == "win32":
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            p = str(dst).replace("'", "''")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -LiteralPath '{p}'"],
                               creationflags=flags, timeout=15)
            clip = r.returncode == 0
        except Exception:
            pass
        try:
            subprocess.Popen(["explorer", "/select,", str(dst)], creationflags=flags)
        except Exception:
            pass
    return {"ok": True, "clip": clip, "path": str(dst)}


def main() -> None:
    global PHONE_URL, PORT
    # une 2e fenêtre lancée pendant qu'Apex tourne ne doit pas effacer le journal de celui qui tourne
    if already_running() and "--demo" not in sys.argv:
        print("\n  Apex Radio tourne déjà : j'ouvre le tableau de bord existant.")
        desktop.show_existing(f"http://localhost:{PORT}")
        sys.exit(0)
    keep_previous_journal()
    log = open(LOCAL / "journal.txt", "w", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    print(f"Python {sys.version.split()[0]} · {sys.platform}")
    # (1.2.10 mettait Apex en priorité « inférieure à la normale » : quand le jeu occupe le processeur, la lecture
    # rapide (spotter, analyse du setup) n'était plus assez souvent lue. On reste en priorité normale.)
    ensure_packages()
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="course simulée, sans le jeu")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-tray", action="store_true", help="pas d'icône près de l'horloge")
    args = ap.parse_args()

    PHONE_URL = f"http://{local_ip()}:{PORT}/tel"
    if already_running() and not replace_other_mode(args.demo):
        # avant de charger la voix : on rouvre juste la fenêtre existante
        print("\n  Apex Radio tourne déjà : j'ouvre le tableau de bord existant.")
        desktop.show_existing(f"http://localhost:{PORT}")
        sys.exit(0)
    state = State()
    state.demo = args.demo
    server = None
    for port in PORTS:
        if _port_busy(port):
            if is_apex(port):
                print("\n  Apex Radio tourne déjà : j'ouvre le tableau de bord existant.")
                print("  (pour passer en démo ou en direct, clique d'abord sur QUITTER dans le tableau de bord)\n")
                desktop.show_existing(f"http://localhost:{port}")
                sys.exit(0)
            print(f"  Le port {port} est déjà pris par un autre logiciel (ex. Pimax Play) : j'essaie le suivant.")
            continue
        try:
            server = ApexServer(("0.0.0.0", port), make_handler(state))
            PORT = port
            break
        except OSError:
            print(f"  Le port {port} est déjà pris : j'essaie le suivant.")
    if server is None:
        print("  Aucun port libre entre 8765 et 8775 : ferme les autres logiciels et relance Apex Radio.")
        sys.exit(1)
    try:
        PORT_FILE.write_text(str(PORT))
    except OSError:
        pass
    PHONE_URL = f"http://{local_ip()}:{PORT}/tel"
    threading.Thread(target=loop, args=(state, args.demo), daemon=True).start()
    if not args.demo:
        threading.Thread(target=autolaunch_lmu, args=(state,), daemon=True).start()
    UPD.start()
    url = f"http://localhost:{PORT}"
    print("=" * 56)
    print(f"  APEX//RADIO {UPD.version} — " + ("MODE DÉMO" if args.demo else "Le Mans Ultimate / Assetto Corsa EVO / Automobilista 2"))
    print(f"  Tableau de bord : {url}")
    print(f"  Sur téléphone : {PHONE_URL}")
    print(f"  Tes données : {DATA}")
    if MIGRATED:
        print(f"  Données reprises de l'ancien dossier : {', '.join(MIGRATED)}")
    print("=" * 56)
    desktop.app_id()
    tray = desktop.Tray(state, url, PHONE_URL, state.radio.cfg, save_config)
    tray_ok = not args.no_tray and tray.available()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if tray_ok:
        state.tray = tray
        tray.run(detached=True)   # icône près de l'horloge, à côté de la fenêtre
    win = desktop.AppWindow(url, hide_on_close=tray_ok, on_hidden=tray.hint if tray_ok else None)
    if not args.no_browser and win.available():
        try:
            win.run()             # fenêtre Apex Radio, jusqu'à « Quitter »
        except Exception as e:
            print(f"  Fenêtre intégrée impossible ({e.__class__.__name__}: {e}), fenêtre Edge à la place.")
            desktop.WINDOW = None
            desktop.open_app_window(url)
    elif not args.no_browser:
        threading.Timer(1.0, lambda: desktop.open_app_window(url)).start()
    try:
        threading.Event().wait()  # la radio tourne jusqu'à « Quitter » (bouton ⏻ ou icône)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
