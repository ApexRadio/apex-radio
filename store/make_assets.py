"""Logos du paquet Microsoft Store, dessinés à partir de apex.ico (Pillow).
Usage : python make_assets.py <apex.ico> <dossier de sortie>"""
import sys
from pathlib import Path
from PIL import Image

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
ico = Image.open(src)
sizes = getattr(ico, "info", {}).get("sizes") or [ico.size]
ico.size = max(sizes)
logo = ico.convert("RGBA")

def square(n, pad=0.0):
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    k = int(n * (1 - 2 * pad))
    im.alpha_composite(logo.resize((k, k), Image.LANCZOS), ((n - k) // 2, (n - k) // 2))
    return im

# fichiers sans qualificatif d'échelle : pas besoin de resources.pri (makepri), le manifeste les trouve tels quels
for name, n, pad in (("Square44x44Logo", 44, 0.0), ("Square150x150Logo", 150, 0.12), ("StoreLogo", 50, 0.0)):
    square(n, pad).save(out / f"{name}.png")
w, h = 310, 150
im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
k = int(h * 0.76)
im.alpha_composite(logo.resize((k, k), Image.LANCZOS), ((w - k) // 2, (h - k) // 2))
im.save(out / "Wide310x150Logo.png")
print("logos OK :", ", ".join(sorted(p.name for p in out.glob("*.png"))))
