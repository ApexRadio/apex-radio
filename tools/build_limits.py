"""
Construit lmu_limits.json à partir d'un relevé compact du garage : {fichier: {"tree": ..., "garage": {...}}}.

  python tools/build_limits.py relevé_compact.json
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from garage_limits import build

if __name__ == "__main__":
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    res, unk = build(src)
    old = Path(__file__).resolve().parent.parent / "lmu_limits.json"
    try:
        cur = json.loads(old.read_text(encoding="utf-8"))
    except Exception:
        cur = {}
    cur.update(res)
    old.write_text(json.dumps(dict(sorted(cur.items())), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(res)} voitures ajoutées / mises à jour, {len(cur)} au total")
    for k, v in res.items():
        print(f"  {v['name']:40s} {len(v['limits'])} réglages")
    if unk:
        print("non reliés :", ", ".join(unk))
