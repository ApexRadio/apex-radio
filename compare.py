"""
Page « Comparer mes tours » : les courbes enregistrées par reflap.py (Documents\\Apex Radio\\laps),
avec la carte du circuit et ses virages, pour mettre deux tours l'un sur l'autre.
"""

from __future__ import annotations

import json
import re

from reflap import LAPS


def listing() -> list[dict]:
    out = []
    for f in sorted(LAPS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": f.stem, "game": d.get("game"), "track": d.get("track"), "car": d.get("car"), "wet": bool(d.get("wet")),
                        "best": (d.get("best") or {}).get("lap"), "n": len(d.get("recent") or []),
                        "shared": len(d.get("shared") or []),
                        "date": ((d.get("recent") or [{}])[0]).get("date")})
        except Exception:
            pass
    return out


def get(name: str) -> dict | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name or ""):
        return None
    f = LAPS / f"{name}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    d["map"], d["corners"] = None, []
    try:   # carte et virages du circuit, sans toucher à ceux de la séance en cours
        import cornernames
        from trackmap import TrackMap
        keep = dict(getattr(cornernames, "ACTIVE", {}) or {})
        tm = TrackMap()
        tm._load(d.get("track") or "")
        if tm.saved:
            d["map"] = tm.points()
            d["corners"] = [{"id": c["id"], "start": c["start"], "end": c["end"], "mid": c["mid"],
                             "name": list(c["name"]) if isinstance(c.get("name"), (list, tuple)) else None}
                            for c in tm.corners()]
        cornernames.ACTIVE = keep
    except Exception as e:
        print(f"  Comparer : carte indisponible ({e.__class__.__name__})")
    return d


# ------------------------------------------------------------------ partage de tours entre pilotes
SHARED_DIR = LAPS.parent / "tours partagés"
MAX_SHARED = 20


def _safe(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(s or "")).strip()[:60] or "?"


def reveal(dst) -> bool:
    """Met le fichier dans le presse-papiers (Ctrl+V dans Discord) et le montre dans l'Explorateur."""
    clip = False
    import sys
    if sys.platform == "win32":
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            p = str(dst).replace("'", "''")
            clip = subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -LiteralPath '{p}'"],
                                  creationflags=flags, timeout=15).returncode == 0
        except Exception:
            pass
        try:
            subprocess.Popen(["explorer", "/select,", str(dst)], creationflags=flags)
        except Exception:
            pass
    return clip


def export(name: str, k: str, driver: str) -> dict:
    """« Partager ce tour » : un petit fichier .apexlap dans Documents\\Apex Radio\\tours partagés, mis dans le
    presse-papiers (Ctrl+V dans Discord) et montré dans l'Explorateur."""
    d = get(name)
    if not d:
        return {"ok": False}
    if k == "best":
        lap = d.get("best")
    elif k.startswith("r") and k[1:].isdigit():
        lap = (d.get("recent") or [None] * 99)[int(k[1:])] if int(k[1:]) < len(d.get("recent") or []) else None
    elif k.startswith("s") and k[1:].isdigit() and int(k[1:]) < len(d.get("shared") or []):
        lap = d["shared"][int(k[1:])]
        driver = lap.get("driver") or driver
    else:
        lap = None
    if not lap:
        return {"ok": False}
    out = {"apexlap": 1, "game": d.get("game"), "track": d.get("track"), "car": d.get("car"), "wet": bool(d.get("wet")),
           "driver": (driver or "Pilote")[:40], **{x: lap.get(x) for x in ("lap", "date", "L", "v", "b", "t")}}
    m, s = divmod(out["lap"] or 0, 60)
    fn = f"{_safe(out['track'])} - {_safe(out['car'])} - {int(m)}'{s:06.3f} - {_safe(out['driver'])}.apexlap"
    try:
        SHARED_DIR.mkdir(parents=True, exist_ok=True)
        dst = SHARED_DIR / fn
        dst.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": e.__class__.__name__}
    clip = reveal(dst)
    return {"ok": True, "clip": clip, "file": fn}


def import_lap(x: dict) -> dict:
    """Tour d'un autre pilote (fichier .apexlap glissé dans la page) : rangé avec tes tours du même circuit/voiture."""
    try:
        if x.get("apexlap") != 1 or not x.get("track") or not x.get("car"):
            return {"ok": False, "error": "format"}
        lap = float(x["lap"])
        arrs = {k: [float(v) for v in x[k]][:600] for k in ("v", "b", "t")}
        if not (10 < lap < 3600) or min(len(a) for a in arrs.values()) < 400:
            return {"ok": False, "error": "format"}
    except Exception:
        return {"ok": False, "error": "format"}
    from reflap import RefLap
    key = f"{x.get('game') or 'lmu'} | {x['track']} | {x['car']}" + (" | pluie" if x.get("wet") else "")
    f = LAPS / RefLap._file(key).name
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        d = {"key": key, "game": x.get("game") or "lmu", "track": x["track"], "car": x["car"], "best": None, "recent": [],
             "wet": bool(x.get("wet"))}
    item = {"lap": round(lap, 3), "date": str(x.get("date") or "")[:16], "L": float(x.get("L") or 0) or None,
            "driver": str(x.get("driver") or "?")[:40], **arrs}
    sh = [s for s in (d.get("shared") or []) if not (s.get("driver") == item["driver"] and abs(s["lap"] - item["lap"]) < 0.001)]
    d["shared"] = sorted(sh + [item], key=lambda s: s["lap"])[:MAX_SHARED]
    LAPS.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    return {"ok": True, "id": f.stem, "track": x["track"], "car": x["car"]}
