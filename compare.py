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
            out.append({"id": f.stem, "game": d.get("game"), "track": d.get("track"), "car": d.get("car"),
                        "best": (d.get("best") or {}).get("lap"), "n": len(d.get("recent") or []),
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
