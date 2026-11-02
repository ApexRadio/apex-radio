"""
Sonde de l'interface locale de LMU (étape 4, phase 1) — LECTURE SEULE.

LMU expose une interface web sur http://localhost:6397 (utilisée par ses propres menus).
On l'interroge uniquement en lecture (requêtes GET) pour découvrir le format du menu
des stands. Rien n'est envoyé ni modifié dans le jeu.
Résultat enregistré dans lmu_api_probe.json (dossier d'Apex Radio).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "lmu_api_probe.json"
BASE = "http://localhost:6397"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # jamais de proxy pour le PC local
ENDPOINTS = [
    "/rest/garage/PitMenu/receivePitMenu",
    "/rest/garage/PitMenu",
    "/rest/garage/UIScreen/RepairAndRefuel",
    "/rest/garage/UIScreen/PitMenu",
    "/rest/garage/getPlayerGarageData",
    "/rest/garage/summary",
    "/rest/strategy/usage",
    "/rest/strategy/pitstop-estimate",
    "/rest/sessions/weather",
    "/rest/sessions/getSessionsInfoForEvent",
    "/rest/sessions",
    "/rest/watch/sessionInfo",
    "/rest",
    "/swagger/index.html",
    "/swagger/swagger-initializer.js",
    "/swagger/v1/swagger.json",
    "/swagger/swagger.json",
    "/swagger-ui/index.html",
    "/openapi.json",
    "/api-docs",
    "/",
]


def _get(path: str) -> dict:
    req = urllib.request.Request(BASE + path, method="GET", headers={"Accept": "application/json"})
    try:
        with _OPENER.open(req, timeout=3) as r:
            body = r.read(60000).decode("utf-8", "replace")
            out = {"status": r.status, "type": r.headers.get("Content-Type", "")}
    except urllib.error.HTTPError as e:
        body = e.read(4000).decode("utf-8", "replace")
        out = {"status": e.code, "type": e.headers.get("Content-Type", "") if e.headers else ""}
    except Exception as e:
        return {"error": repr(e)}
    try:
        out["json"] = json.loads(body)
    except Exception:
        out["text"] = body[:8000]
    return out


class Probe:
    """Fait une capture à chaque étape : jeu lancé, en piste, au stand (au plus une fois chacune)."""

    def __init__(self) -> None:
        self.done = set()
        try:
            self.data = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        self.busy = False

    def update(self, s) -> None:
        if not s.connected or self.busy:
            return
        stage = "au_stand" if s.in_pits else "en_piste" if s.on_track else "menu"
        if stage in self.done:
            return
        self.done.add(stage)
        self.busy = True
        threading.Thread(target=self._run, args=(stage, s.session, s.track, s.car), daemon=True).start()

    def _run(self, stage: str, session: str, track: str, car: str) -> None:
        try:
            res = {"quand": time.strftime("%d/%m/%Y %H:%M:%S"), "session": session, "circuit": track,
                   "voiture": car, "reponses": {}}
            for ep in ENDPOINTS:
                res["reponses"][ep] = _get(ep)
            self.data[stage] = res
            OUT.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
            ok = sum(1 for r in res["reponses"].values() if r.get("status") == 200)
            print(f"  Sonde LMU ({stage}) : {ok} réponses enregistrées dans lmu_api_probe.json")
        finally:
            self.busy = False
