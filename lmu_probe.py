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


# Relevé complet du garage : COUPÉ. Le 27/11/2026, LMU a planté 5 fois pendant les relevés (jamais en 2 semaines avant) :
# trop de demandes au jeu pendant qu'il charge le garage. Les limites des voitures sont déjà relevées (lmu_garage/).
GARAGE_ON = False
# Toutes les sondes (relevé léger des limites au garage, captures « menu / en piste / au stand ») : COUPÉES depuis la 1.5.1
# par précaution, après un plantage de LMU signalé par un joueur. Apex ne pose plus au jeu que les questions dont il a
# besoin (menu des stands, setup chargé…). Pour les activer sur un PC précis (relever une voiture qui manque), créer le fichier
# %LOCALAPPDATA%\Apex Radio\releve_garage.txt.
try:
    LIGHT_ON = (LOCAL / "releve_garage.txt").exists()
except Exception:
    LIGHT_ON = False
GARAGE_DIR = OUT.parent / "lmu_garage"     # un fichier par voiture : tout le menu des réglages vu par le jeu
# jamais d'appel qui pourrait AGIR dans le jeu, même en GET (charger, enregistrer, quitter…)
DENY = ("load", "save", "delete", "remove", "reset", "set", "send", "apply", "start", "stop", "exit", "quit",
        "restart", "drive", "join", "leave", "kick", "ban", "buy", "purchase", "write", "update", "create",
        "rename", "copy", "toggle", "press", "click", "select", "change", "post", "put", "upload", "install",
        "receive", "request", "launch", "go", "skip", "end", "finish", "retire", "pit", "chat", "vote")
WANT = ("garage", "setup", "vehicle", "car", "tire", "tyre", "upgrade")
GARAGE_KNOWN = ("/rest/garage/getPlayerGarageData", "/rest/garage/summary")


def _safe_paths(schema: dict) -> list[str]:
    """Chemins GET sans paramètre qui parlent du garage / setup, et dont aucun mot ne ressemble à une action."""
    import re
    out = []
    for path, ops in ((schema or {}).get("paths") or {}).items():
        if "get" not in {k.lower() for k in (ops or {})} or "{" in path or "(" in path:
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
        if not LIGHT_ON or not s.connected or self.busy:
            return
        stage = "au_stand" if s.in_pits else "en_piste" if s.on_track else "menu"
        if GARAGE_ON and getattr(s, "game", "lmu") == "lmu" and s.in_pits and s.car and f"garage|{s.car}" not in self.done:
            # au garage avec une voiture : on relève tout le menu des réglages (crans, mini, maxi) de CETTE voiture
            self.done.add(f"garage|{s.car}")
            self.busy = True
            threading.Thread(target=self._garage, args=(s.car_class, s.car, s.track), daemon=True).start()
            return
        if LIGHT_ON and getattr(s, "game", "lmu") == "lmu":
            self._light_tick(s)
            if self.busy:
                return
        if stage in self.done:
            return
        self.done.add(stage)
        self.busy = True
        threading.Thread(target=self._run, args=(stage, s.session, s.track, s.car), daemon=True).start()

    # ---------------------------------------------------------- sonde LÉGÈRE (sans risque)
    def _light_tick(self, s) -> None:
        """Au garage, voiture immobile depuis 45 s : on relève UNE fois le menu des réglages de cette voiture
        (2 petites questions au jeu, les mêmes que la sonde « au stand » posait depuis des semaines sans souci)."""
        if not s.in_pits or not s.car or getattr(s, "speed", 0) > 1:
            self._lt = None
            return
        if getattr(self, "_lt", None) is None or self._lt[0] != s.car:
            self._lt = (s.car, time.monotonic())
            return
        ld = self.__dict__.setdefault("light_done", set())
        tries = self.__dict__.setdefault("light_tries", {})      # voiture -> (essais, dernier essai)
        n, last = tries.get(s.car, (0, -1e9))
        now = time.monotonic()
        if s.car in ld or now - self._lt[1] < 45 or n >= 5 or now - last < 30:
            return
        tries[s.car] = (n + 1, now)
        ld.add(s.car)
        self.busy = True
        threading.Thread(target=self._light, args=(s.car,), daemon=True).start()

    def _light(self, car: str) -> None:
        import re
        try:
            sm = _get("/rest/garage/summary", 400000).get("json") or {}
            disp = ((sm.get("car") or {}).get("displayProperties") or {})
            if disp.get("displayName") != car:
                print(f"  Sonde légère : le garage montre encore « {disp.get('displayName')} », pas « {car} » : je réessaierai")
                self.light_done.discard(car)
                return
            tree = disp.get("fullTreePath") or ""
            model = tree.split(",")[-1].strip()
            dst = GARAGE_DIR / ("light_" + re.sub(r"[^A-Za-z0-9_-]+", "_", model)[:80] + ".json")
            if not model or dst.exists():
                return
            time.sleep(1)
            g = _get("/rest/garage/getPlayerGarageData", 400000).get("json")
            if not isinstance(g, dict) or len(g) < 20:
                self.light_done.discard(car)
                return
            sm2 = _get("/rest/garage/summary", 400000).get("json") or {}
            if (((sm2.get("car") or {}).get("displayProperties") or {}).get("displayName")) != car:
                self.light_done.discard(car)          # la voiture a changé pendant le relevé : on recommencera
                return
            keep = {k: {x: v.get(x) for x in ("available", "minValue", "maxValue")} for k, v in g.items() if isinstance(v, dict)}
            GARAGE_DIR.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps({"tree": tree, "car": car, "quand": time.strftime("%d/%m/%Y %H:%M"), "garage": keep},
                                      ensure_ascii=False), encoding="utf-8")
            print(f"  Limites des réglages relevées : {model} ({len(keep)} réglages)")
        except Exception as e:
            print(f"  Sonde légère : {e!r}")
        finally:
            self.busy = False

    def _garage(self, car_class: str, car: str, track: str) -> None:
        import re
        try:
            GARAGE_DIR.mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{car_class}_{car}")[:80] or "voiture"
            dst = GARAGE_DIR / f"{name}.json"
            best, schema, paths, res = -1, {}, [], {}
            # plusieurs relevés (5 s, 30 s, 90 s) : certains écrans du garage ne répondent qu'une fois ouverts ;
            # on garde le relevé le plus complet
            for wait in (5, 25, 60):
                time.sleep(wait)
                schema = _get("/swagger-schema.json", 4_000_000).get("json") or schema
                # les adresses sûres connues (menu des réglages complet avec mini / maxi, résumé du garage), plus celles
                # trouvées dans la liste du jeu
                paths = sorted(set(GARAGE_KNOWN) | set(_safe_paths(schema)))
                cur = {"quand": time.strftime("%d/%m/%Y %H:%M:%S"), "classe": car_class, "voiture": car, "circuit": track,
                       "chemins": paths, "reponses": {ep: _get(ep, 600000) for ep in paths}}
                size = sum(len(json.dumps(r)) for r in cur["reponses"].values() if r.get("status") == 200)
                # le fichier porte le MODÈLE de la voiture (« Aston Martin Vantage AMR LMGT3 »), pas l'équipe / la livrée
                try:
                    tree = cur["reponses"]["/rest/garage/summary"]["json"]["car"]["displayProperties"]["fullTreePath"]
                    model = tree.split(",")[-1].strip()
                    cur["modele"] = model
                    nd = GARAGE_DIR / (re.sub(r"[^A-Za-z0-9_-]+", "_", model)[:80] + ".json")
                    if nd != dst:
                        if dst.exists() and best >= 0:
                            dst.unlink(missing_ok=True)
                        dst = nd
                except Exception:
                    pass
                if size > best:
                    best, res = size, cur
                    dst.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
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
