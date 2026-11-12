# Deux styles d'accueil : la livrée Apex (photo) ou le grand logo A//.
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import build_profile as b

S, N = b.S, b.N
REPO = Path(__file__).resolve().parents[2]


def _menu_overlay(f, t):
    pulse = 0.55 + 0.45 * math.sin(2 * math.pi * t)
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 150))
    f.alpha_composite(sh)
    lay, bl = b.glow_layer(lambda g: g.rounded_rectangle([10, 10, S - 11, S - 11], 18, outline=b.CYAN + (255,), width=3), (S, S), 5)
    b.stack(f, lay, bl, pulse)
    ic = ImageFont.truetype(b.ICONF, 50)
    lay, bl = b.glow_layer(lambda g: g.text((S / 2, 58), b.icon_char("menu-2"), font=ic, fill=b.WHITE + (255,), anchor="mm"), (S, S), 6)
    b.stack(f, lay, bl, 0.7)
    lay, bl = b.glow_layer(lambda g: g.text((S / 2, 108), "MENU", font=b.font(24), fill=b.CYAN + (255,), anchor="mm"), (S, S), 4)
    b.stack(f, lay, bl, pulse)


G = 44   # espace entre deux touches sur le vrai Stream Deck (en pixels d'image)


def livery():
    """photo de la livrée sur les 15 touches, découpée en tenant compte de l'espace entre les touches
    (comme une vitre derrière une grille) ; cadrage choisi pour que les roues soient le moins coupées possible"""
    W, H = 5 * S + 4 * G, 3 * S + 2 * G
    src = Image.open(REPO / "docs/livree/ApexRadio-livree-Oreca-LMP2.jpg").convert("RGBA")
    cw, x0, y0 = 1560, 250, 0
    ch = int(cw * H / W)
    pic = src.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.LANCZOS)
    frames = []
    for i in range(N):
        t = i / N
        im = pic.copy()
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        x = -300 + t * (W + 600)
        d.polygon([(x, 0), (x + 90, 0), (x - 40, H), (x - 130, H)], fill=(255, 255, 255, 55))
        im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(18)))
        frames.append(im)
    return frames


def logo():
    """grand logo A// au centre (3 x 3 touches), ondes radio sur les côtés"""
    W, H = 5 * S, 3 * S
    src = Image.open(REPO / "apex.ico")
    src.size = (256, 256)
    lg = src.convert("RGBA")
    # on retire le fond carré de l'icône : on garde seulement les pixels lumineux
    px = lg.load()
    for y in range(256):
        for x in range(256):
            r, g, bb, a = px[x, y]
            lum = max(r, g, bb)
            px[x, y] = (r, g, bb, 0 if lum < 70 else min(255, int((lum - 70) * 2.2)))
    lg = lg.crop((30, 20, 226, 226)).resize((int(H * 0.95), int(H * 0.95)), Image.LANCZOS)
    frames = []
    for i in range(N):
        t = i / N
        im = Image.new("RGBA", (W, H), b.BG + (255,))
        grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(grid)
        off = int(t * 24) % 24
        for x in range(0, W, 24):
            d.line([(x, 0), (x, H)], fill=b.CYAN + (20,))
        for y in range(-24 + off, H, 24):
            d.line([(0, y), (W, y)], fill=b.CYAN + (20,))
        im.alpha_composite(grid)
        cx, cy = W / 2, H / 2
        for k in range(3):
            p = (t + k / 3) % 1
            rr = H * 0.42 + p * W * 0.32
            a = int(220 * (1 - p))
            lay, bl = b.glow_layer(lambda g: (g.arc([cx - rr, cy - rr, cx + rr, cy + rr], 150, 210, fill=b.PINK + (a,), width=5),
                                              g.arc([cx - rr, cy - rr, cx + rr, cy + rr], -30, 30, fill=b.PINK + (a,), width=5)), (W, H), 6)
            b.stack(im, lay, bl, 0.9)
        pulse = 0.6 + 0.4 * math.sin(2 * math.pi * t)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay.alpha_composite(lg, (int(cx - lg.width / 2), int(cy - lg.height / 2)))
        b.stack(im, lay, lay.filter(ImageFilter.GaussianBlur(14)), pulse)
        frames.append(im)
    return frames


def keys_from(full, gap=0):
    keys = {}
    p = S + gap
    for r in range(3):
        for c in range(5):
            fr = [f.crop((c * p, r * p, c * p + S, r * p + S)) for f in full]
            if (c, r) == (0, 0):
                for k, f in enumerate(fr):
                    _menu_overlay(f, k / N)
            keys[(c, r)] = fr
    return keys


if __name__ == "__main__":
    for name, fn in (("livree", livery), ("logo", logo)):
        prev = b.splash_preview(keys_from(fn(), G if name == "livree" else 0))
        b.save_gif(prev, Path(__file__).parent / "preview" / f"accueil-{name}.gif")
        prev[8].convert("RGB").save(f"/tmp/acc-{name}.png")
    print("ok")
