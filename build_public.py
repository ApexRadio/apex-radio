"""
Prépare la version publique d'Apex Radio dans un dossier à part (et un .zip),
sans aucune donnée personnelle : pas de config, records, débriefs, cartes, setups, journal, modèles.
Usage : python build_public.py   ->  ../ApexRadio-public/ et ../ApexRadio-<version>.zip
"""
import shutil
import zipfile
from pathlib import Path

VERSION = "1.0.0"
HERE = Path(__file__).parent
OUT = HERE.parent / "ApexRadio-public"
FILES = ["app.py", "alerts.py", "behavior.py", "debrief.py", "i18n.py", "incidents.py", "laptimes.py", "lmu_probe.py",
         "phrases.py", "pitmenu.py", "questions.py", "radio.py", "setups.py", "strategy.py", "tactics.py", "telemetry.py", "trackmap.py",
         "voice.py", "requirements.txt", "Lancer.bat", "Demo.bat", "apex.ico", "LICENSE", "README.md",
         "THIRD_PARTY_LICENSES.txt", "LISEZMOI.txt"]
DIRS = ["ui", "vendor"]

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir()
for f in FILES:
    shutil.copy2(HERE / f, OUT / f)
for d in DIRS:
    shutil.copytree(HERE / d, OUT / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
(OUT / "VERSION").write_text(VERSION, encoding="utf-8")
z = HERE.parent / f"ApexRadio-{VERSION}.zip"
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            zf.write(p, Path("ApexRadio") / p.relative_to(OUT))
print(f"Version publique : {OUT}\nArchive : {z}")
