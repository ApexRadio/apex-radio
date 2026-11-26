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
try:   # dossier technique (l'appli installée par le Microsoft Store ne peut pas écrire dans son propre dossier)
    from paths import LOCAL
    OUT = LOCAL / "lmu_api_probe.json"
except Exception:
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
    "/swagger-schema.json",
    "/swagger/index.html",
    "/swagger/swagger-initializer.js",
    "/swagger/v1/swagger.json",
    "/swagger/swagger.json",
    "/swagger-ui/index.html",
    "/openapi.json",
    "/api-docs",
    "/",
]


def _get(path: str, limit: int = 60000) -> dict:
    req = urllib.request.Request(BASE + path, method="GET", headers={"Accept": "application/json"})
    try:
        with _OPENER.open(req, timeout=3) as r:
            body = r.read(limit).decode("utf-8", "replace")
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


GARAGE_DIR = OUT.parent / "lmu_garage"     # un fichier par voiture : tout le menu des réglages vu par le jeu
# jamais d'appel qui pourrait AGIR dans le jeu, même en GET (charger, enregistrer, quitter…)
DENY = ("load", "save", "delete", "remove", "reset", "set", "send", "apply", "start", "stop", "exit", "quit",
        "restart", "drive", "join", "leave", "kick", "ban", "buy", "purchase", "write", "update", "create",
        "rename", "copy", "toggle", "press", "click", "select", "change", "post", "put", "upload", "install",
        "receive", "request", "launch", "go", "skip", "end", "finish", "retire", "pit", "chat", "vote")
WANT = ("garage", "setup", "vehicle", "car", "tire", "tyre", "upgrade")


def _safe_paths(schema: dict) -> list[str]:
    """Chemins GET sans paramètre qui parlent du garage / setup, et dont aucun mot ne ressemble à une action."""
    import re
    out = []
    for path, ops in ((schema or {}).get("paths") or {}).items():
        if "get" not in {k.lower() for k in (ops or {})} or "{" in path:
            continue
        low = path.lower()
        if not any(w in low for w in WANT):
            continue
        words = re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", path).lower())
        if any(w in DENY for w in words):
            continue
        out.append(path)
    return sorted(out)


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
        if getattr(s, "game", "lmu") == "lmu" and s.in_pits and s.car and f"garage|{s.car}" not in self.done:
            # au garage avec une voiture : on relève tout le menu des réglages (crans, mini, maxi) de CETTE voiture
            self.done.add(f"garage|{s.car}")
            self.busy = True
            threading.Thread(target=self._garage, args=(s.car_class, s.car, s.track), daemon=True).start()
            return
        if stage in self.done:
            return
        self.done.add(stage)
        self.busy = True
        threading.Thread(target=self._run, args=(stage, s.session, s.track, s.car), daemon=True).start()

    def _garage(self, car_class: str, car: str, track: str) -> None:
        import re
        try:
            time.sleep(4)        # le temps que le menu du garage soit prêt
            schema = _get("/swagger-schema.json").get("json") or {}
            paths = _safe_paths(schema)
            res = {"quand": time.strftime("%d/%m/%Y %H:%M:%S"), "classe": car_class, "voiture": car, "circuit": track,
                   "chemins": paths, "reponses": {}}
            for ep in paths:
                res["reponses"][ep] = _get(ep, 600000)
            GARAGE_DIR.mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{car_class}_{car}")[:80] or "voiture"
            (GARAGE_DIR / f"{name}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
            if schema:
                (GARAGE_DIR / "_schema.json").write_text(json.dumps(schema, indent=1, ensure_ascii=False), encoding="utf-8")
            ok = sum(1 for r in res["reponses"].values() if r.get("status") == 200)
            print(f"  Sonde garage LMU : {car} — {ok}/{len(paths)} réponses enregistrées (lmu_garage)")
        except Exception as e:
            print(f"  Sonde garage LMU : {e!r}")
        finally:
            self.busy = False

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
