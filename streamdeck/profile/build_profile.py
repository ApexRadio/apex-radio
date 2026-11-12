# Construit le profil Stream Deck « Apex Radio » (15 touches) livré avec le plugin :
# images animées (GIF) créées ici, pages et dossiers, puis le fichier .streamDeckProfile.
# Lancer : python3 profile/build_profile.py   (depuis le dossier streamdeck)
import base64, io, json, math, sys, uuid, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
OUT = HERE.parent / "com.apexradio.streamdeck.sdPlugin" / "profiles" / "Apex Radio.streamDeckProfile"
PLUGIN = "com.apexradio.streamdeck"
DEVICE = sys.argv[1] if len(sys.argv) > 1 else ""   # identifiant d'un Stream Deck précis (sinon : aucun)

S = 144                 # taille d'une touche
N = 24                  # images par animation
MS = 70                 # durée d'une image (ms)
BG = (6, 9, 15)
CYAN, PINK, AMBER, GREEN, RED, WHITE = (34, 227, 255), (255, 46, 136), (255, 176, 46), (46, 229, 157), (255, 59, 92), (235, 245, 255)

BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
ICONF = str(HERE / "fonts" / "tabler-icons.ttf")
CODES = json.load(open(HERE / "fonts" / "tabler-codes.json"))


def font(size):
    return ImageFont.truetype(BOLD, size)


def icon_char(name):
    return chr(int(CODES[name], 16))


def glow_layer(draw_fn, size, blur):
    """dessine sur un calque transparent, renvoie (net, flou) pour faire un néon"""
    lay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(lay))
    return lay, lay.filter(ImageFilter.GaussianBlur(blur))


def stack(base, lay, blur, glow_alpha):
    if glow_alpha > 0:
        g = blur.copy()
        g.putalpha(g.getchannel("A").point(lambda a: int(a * glow_alpha)))
        base.alpha_composite(g)
        base.alpha_composite(g)
    base.alpha_composite(lay)


def save_gif(frames, path):
    pal = [f.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    buf = io.BytesIO()
    pal[0].save(buf, "GIF", save_all=True, append_images=pal[1:], duration=MS, loop=0, disposal=1, optimize=False)
    path.write_bytes(buf.getvalue())


def border_point(t):
    """point sur le contour arrondi de la touche, t entre 0 et 1"""
    m, w = 10, S - 20
    p = t * 4 * w
    side, d = int(p // w) % 4, p % w
    return [(m + d, m), (m + w, m + d), (m + w - d, m + w), (m, m + w - d)][side]


# ------------------------------------------------------------------ style des touches (style A)
# fond noir, coin bleu en haut à gauche, coin rose en bas à droite (ils pulsent doucement),
# grosse icône blanche, nom en gras en bas
KEY_BG = (8, 8, 10)
CORNER = 24


def label_font(text, maxw, start=24):
    sz = start
    while sz > 13 and font(sz).getlength(text) > maxw:
        sz -= 1
    return font(sz)


def _dim(c, k):
    return tuple(int(v * k) for v in c)


import numpy as np

_YY, _XX = np.mgrid[0:S, 0:S].astype(np.float32)
_ANG = (np.arctan2(_YY - S / 2, _XX - S / 2) / (2 * np.pi)) % 1.0


def _frame_mask():
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle([2, 2, S - 3, S - 3], 20, outline=255, width=7)
    return np.asarray(m, dtype=np.float32) / 255


_FRAME = _frame_mask()


def key_base(t, kind="cmd"):
    """animation qui défile.
    "cmd"    : rayures diagonales qui glissent dans les coins (bleu en haut à gauche, rose en bas à droite)
    "folder" : cadre néon dont le bleu et le rose tournent autour de la touche"""
    rgb = np.zeros((S, S, 3), np.float32)
    rgb[:] = KEY_BG
    cyan, pink = np.array(CYAN, np.float32), np.array(PINK, np.float32)
    if kind == "folder":
        mix = 0.5 + 0.5 * np.cos(2 * np.pi * (_ANG - t))          # 1 = bleu, 0 = rose
        col = mix[..., None] * cyan + (1 - mix[..., None]) * pink
        # petit éclat blanc qui fait le tour
        spark = np.clip(1 - np.abs(((_ANG - t + 0.5) % 1.0) - 0.5) * 18, 0, 1)[..., None]
        col = col * (1 - spark) + 255 * spark
        a = _FRAME[..., None]
        rgb = rgb * (1 - a) + col * a
    else:
        period, size = 16.0, 60.0
        d1 = _XX + _YY                       # coin haut gauche
        d2 = (S - 1 - _XX) + (S - 1 - _YY)   # coin bas droit
        for d, c in ((d1, cyan), (d2, pink)):
            stripe = (((d + t * period) % period) < period * 0.55) & (d < size)
            solid = d < 22                   # petit triangle plein dans l'angle
            m = (stripe | solid)[..., None]
            rgb = np.where(m, c, rgb)
    im = Image.fromarray(rgb.clip(0, 255).astype(np.uint8), "RGB").convert("RGBA")
    return im, ImageDraw.Draw(im)


def tile(icon, label, color=None, sub=None, anim="pulse", kind="cmd"):
    """touche : grosse icône épaissie + nom en gros (le Stream Deck affiche les touches en petit)"""
    frames = []
    ic = ImageFont.truetype(ICONF, 76)
    f_label = label_font(label, S - (34 if kind == "folder" else 40), 30)
    for i in range(N):
        t = i / N if anim != "none" else 0.25
        im, d = key_base(t, kind)
        d.text((S / 2, 56 if kind == "folder" else 54), icon_char(icon), font=ic, fill=WHITE, anchor="mm", stroke_width=2, stroke_fill=WHITE)
        d.text((S / 2, 110 if kind == "folder" else 104), label, font=f_label, fill=WHITE, anchor="mm", stroke_width=1, stroke_fill=WHITE)
        frames.append(im)
    return frames


# ------------------------------------------------------------------ touche de réglage (TC +, ABS −…)
def adjust_tile(code, up, color=None):
    """réglage + / − (bandes de course) : grosse flèche verte ou rose qui bouge, sigle en gros"""
    color = color or (GREEN if up else PINK)
    frames = []
    ic = ImageFont.truetype(ICONF, 64)
    arrow = icon_char("arrow-big-up" if up else "arrow-big-down")
    f_code = label_font(code, S - 44, 40)
    for i in range(N):
        t = i / N
        im, d = key_base(t, "cmd")
        dy = 5 * math.sin(2 * math.pi * t) * (-1 if up else 1)
        d.text((S / 2, 48 + dy), arrow, font=ic, fill=color, anchor="mm", stroke_width=3, stroke_fill=color)
        d.text((S / 2, 104), code, font=f_code, fill=WHITE, anchor="mm", stroke_width=1, stroke_fill=WHITE)
        frames.append(im)
    return frames


# touches clavier (codes Windows) : Stream Deck appuie sur la touche réglée dans LMU
def hk(vk, qt):
    empty = {"KeyCmd": False, "KeyCtrl": False, "KeyModifiers": 0, "KeyOption": False, "KeyShift": False, "NativeCode": 146, "QTKeyCode": 33554431, "VKeyCode": -1}
    k = dict(empty, NativeCode=vk, QTKeyCode=qt, VKeyCode=vk)
    return {"Coalesce": True, "Hotkeys": [k, empty, empty, empty]}


def letter(ch):
    return hk(ord(ch), ord(ch))


# ------------------------------------------------------------------ accueil animé (une lettre par touche)
LAYOUT = [["MENU", "A", "P", "E", "X"],
          ["R", "A", "D", "I", "O"],
          ["EQ", "EQ", "MIC", "EQ", "EQ"]]


def bg_key(t, c, r):
    """fond commun : grille qui défile + balayage rose qui traverse tout le Stream Deck"""
    im = Image.new("RGBA", (S, S), BG + (255,))
    lay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    off = int(t * 24) % 24
    for x in range(0, S, 24):
        d.line([(x, 0), (x, S)], fill=CYAN + (22,))
    for y in range(-24 + off, S, 24):
        d.line([(0, y), (S, y)], fill=CYAN + (22,))
    im.alpha_composite(lay)
    # balayage : une barre rose qui passe de gauche à droite sur les 5 colonnes
    gx = t * 5 * S * 1.4 - S
    x = gx - c * S
    if -40 < x < S + 40:
        l2, b2 = glow_layer(lambda g: g.line([(x, 0), (x - 30, S)], fill=PINK + (120,), width=3), (S, S), 8)
        stack(im, l2, b2, 0.8)
    return im


def splash_key(c, r):
    kind = LAYOUT[r][c]
    frames = []
    big = font(108)
    ic = ImageFont.truetype(ICONF, 64)
    for i in range(N):
        t = i / N
        im = bg_key(t, c, r)
        if kind == "MENU":
            ic2 = ImageFont.truetype(ICONF, 50)
            pulse = 0.55 + 0.45 * math.sin(2 * math.pi * t)
            lay, bl = glow_layer(lambda g: g.rounded_rectangle([10, 10, S - 11, S - 11], 18, outline=CYAN + (255,), width=3), (S, S), 5)
            stack(im, lay, bl, pulse)
            lay, bl = glow_layer(lambda g: g.text((S / 2, 58), icon_char("menu-2"), font=ic2, fill=WHITE + (255,), anchor="mm"), (S, S), 6)
            stack(im, lay, bl, 0.7)
            lay, bl = glow_layer(lambda g: g.text((S / 2, 108), "MENU", font=font(24), fill=CYAN + (255,), anchor="mm"), (S, S), 4)
            stack(im, lay, bl, pulse)
        elif kind == "EQ":
            lay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            for b in range(5):
                k = c * 5 + b
                h = 14 + 80 * abs(math.sin(2 * math.pi * (t * 2 + k * 0.17))) * (0.45 + 0.55 * abs(math.sin(k * 0.9 + t * 6.28)))
                col = CYAN if k % 2 else PINK
                d.rounded_rectangle([12 + b * 25, S - 20 - h, 12 + b * 25 + 16, S - 20], 4, fill=col + (230,))
            bl = lay.filter(ImageFilter.GaussianBlur(5))
            stack(im, lay, bl, 0.7)
        elif kind == "MIC":
            cx, cy = S / 2, S / 2
            for k in range(3):
                p = (t + k / 3) % 1
                rr = 26 + p * 46
                a = int(230 * (1 - p))
                lay, bl = glow_layer(lambda g: (g.arc([cx - rr, cy - rr, cx + rr, cy + rr], 200, 340, fill=PINK + (a,), width=4),
                                                g.arc([cx - rr, cy - rr, cx + rr, cy + rr], 20, 160, fill=PINK + (a,), width=4)), (S, S), 5)
                stack(im, lay, bl, 0.8)
            lay, bl = glow_layer(lambda g: g.text((cx, cy), icon_char("microphone"), font=ic, fill=WHITE + (255,), anchor="mm"), (S, S), 8)
            stack(im, lay, bl, 0.9)
        else:
            # lettre néon ; elles s'allument l'une après l'autre (vague de lumière)
            idx = c + r * 5
            wave = 0.5 + 0.5 * math.sin(2 * math.pi * (t - idx / 10))
            col = CYAN
            lay, bl = glow_layer(lambda g: g.text((S / 2, S / 2 + 4), kind, font=big, fill=col + (255,), anchor="mm"), (S, S), 9)
            stack(im, lay, bl, 0.35 + 0.65 * wave)
            if wave > 0.92:   # petit éclat blanc au sommet de la vague
                lay, bl = glow_layer(lambda g: g.text((S / 2, S / 2 + 4), kind, font=big, fill=WHITE + (110,), anchor="mm"), (S, S), 3)
                stack(im, lay, bl, 0.0)
        frames.append(im)
    return frames


def splash_preview(keys):
    gap = 44
    out = []
    for i in range(N):
        deck = Image.new("RGBA", (5 * S + 6 * gap, 3 * S + 4 * gap), (30, 30, 32, 255))
        for (c, r), fr in keys.items():
            deck.paste(fr[i], (gap + c * (S + gap), gap + r * (S + gap)))
        out.append(deck)
    return out


# ------------------------------------------------------------------ profil
def enc(u):
    """nom de dossier d'une page : identifiant encodé comme le fait le logiciel Stream Deck"""
    return base64.b32hexencode(u.bytes).decode().rstrip("=") + "Z"


class Page:
    def __init__(self, pid=None):
        self.id = uuid.UUID(pid) if pid else uuid.uuid4()
        self.actions = {}
        self.images = {}

    def img(self, frames):
        name = enc(uuid.uuid4()) + ".gif"
        self.images[name] = frames
        return "Images/" + name

    def put(self, col, row, entry):
        self.actions[f"{col},{row}"] = entry

    def manifest(self):
        return {"Controllers": [{"Actions": self.actions, "Type": "Keypad"}], "Icon": "", "Name": ""}


def state(image=None):
    s = {}
    if image:
        s["Image"] = image
    return s


SYS_PLUGIN = {
    "com.elgato.streamdeck.system.hotkey": "Activate a Key Command",
    "com.elgato.streamdeck.profile.openchild": "Create Folder",
    "com.elgato.streamdeck.profile.backtoparent": "Open Parent Folder",
    "com.elgato.streamdeck.system.text": "Text",
}


def entry(uuid_, name, plugin_uuid, plugin_name, plugin_version, settings, st):
    return {"ActionID": str(uuid.uuid4()), "LinkedTitle": True, "Name": name,
            "Plugin": {"Name": plugin_name, "UUID": plugin_uuid, "Version": plugin_version},
            "Resources": None, "Settings": settings, "State": 0, "States": [st], "UUID": uuid_}


def sys_action(uuid_, name, image, settings=None):
    return entry(uuid_, name, uuid_, SYS_PLUGIN[uuid_], "1.0", settings or {}, state(image))


def folder(page, child, frames):
    return sys_action("com.elgato.streamdeck.profile.openchild", "Create Folder", page.img(frames), {"ProfileUUID": str(child.id)})


def back(page):
    return sys_action("com.elgato.streamdeck.profile.backtoparent", "Parent Folder", page.img(tile("arrow-back-up", "RETOUR", PINK, kind="folder")))


def hotkey(page, frames, keys):
    return entry("com.elgato.streamdeck.system.hotkey", "Hotkey", "com.elgato.streamdeck.system.hotkey",
                 "Activate a Key Command", "1.0", keys, state(page.img(frames)))


def decor(page, frames):
    return sys_action("com.elgato.streamdeck.system.text", "Text", page.img(frames),
                      {"Hotkey": {"KeyModifiers": 0, "QTKeyCode": 33554431, "VKeyCode": -1}, "isSendingEnter": False, "isTypingMode": False, "pastedText": ""})


def apex(kind, **settings):
    names = {"radio": "Radio (talk)", "info": "Live info", "spotter": "Spotter on/off", "quiet": "Quiet mode",
             "voice": "Radio on/off", "repeat": "Repeat", "ask": "Question", "launch": "Start LMU"}
    return entry(f"{PLUGIN}.{kind}", names[kind], PLUGIN, "Apex Radio", "0.2.3", settings, state())


def build():
    home = Page("ce525ede-5435-4593-b716-3c63e631989d")
    menu = Page("667299a3-7c6c-4e55-9fcb-b0ab9c611557")
    live = Page("7aa7a9ad-616f-4285-8b7f-7169d18078a4")
    car = Page("5b0c1a52-7d3e-4c1e-9a51-3c8f2e6a1001")
    aids = Page("5b0c1a52-7d3e-4c1e-9a51-3c8f2e6a1002")

    # accueil : la livrée Apex Radio sur les 15 touches ; la touche MENU (en haut à gauche) ouvre le menu
    import home_styles
    keys = home_styles.keys_from(home_styles.livery(), home_styles.G)
    for (c, r), frames in keys.items():
        home.put(c, r, folder(home, menu, frames) if (c, r) == (0, 0) else decor(home, frames))

    # menu
    m = menu
    m.put(0, 0, back(m))
    m.put(1, 0, folder(m, live, tile("chart-bar", "LIVE", CYAN, kind="folder")))
    m.put(2, 0, apex("radio"))
    m.put(3, 0, apex("spotter"))
    m.put(4, 0, apex("quiet"))
    m.put(0, 1, apex("ask", q="fais-moi le point", label="Le point"))
    m.put(1, 1, apex("ask", q="l'état de mes pneus", label="Pneus"))
    m.put(2, 1, apex("ask", q="la météo pour la course", label="Météo"))
    m.put(3, 1, apex("repeat"))
    m.put(4, 1, apex("voice"))
    m.put(0, 2, apex("launch"))
    m.put(1, 2, apex("ask", q="prépare-moi l'arrêt", label="Box"))
    m.put(2, 2, folder(m, car, tile("car", "VOITURE", AMBER, kind="folder")))
    m.put(3, 2, folder(m, aids, tile("adjustments", "AIDES", AMBER, kind="folder")))
    m.put(4, 2, decor(m, tile("video", "BIENTÔT", AMBER, anim="none", kind="folder")))

    # en course : infos en direct
    l = live
    l.put(0, 0, back(l))
    for (c, r), what in {(1, 0): "pos", (2, 0): "fuel", (3, 0): "gap_ahead", (4, 0): "gap_behind",
                         (0, 1): "box", (1, 1): "last", (2, 1): "best"}.items():
        l.put(c, r, apex("info", what=what))
    l.put(3, 1, apex("ask", q="l'état de mes pneus", label="Pneus"))
    l.put(4, 1, apex("ask", q="la météo pour la course", label="Météo"))
    l.put(0, 2, apex("radio"))
    l.put(1, 2, apex("spotter"))
    l.put(2, 2, apex("quiet"))
    l.put(3, 2, apex("repeat"))
    l.put(4, 2, apex("ask", q="fais-moi le point", label="Le point"))

    # voiture : touches de LMU (clavier AZERTY, réglages de Laurent pour l'instant)
    v = car
    v.put(0, 0, back(v))
    v.put(1, 0, hotkey(v, tile("key", "CONTACT", AMBER), letter("I")))
    v.put(2, 0, hotkey(v, tile("engine", "DÉMARRER", AMBER), letter("O")))
    v.put(3, 0, hotkey(v, tile("gauge", "LIMITEUR", AMBER), letter("E")))
    v.put(4, 0, hotkey(v, tile("bulb", "PHARES", AMBER), letter("T")))
    v.put(0, 1, hotkey(v, tile("brightness-up", "APPEL", AMBER), letter("Y")))
    v.put(1, 1, hotkey(v, tile("wiper", "ESSUIE", AMBER), letter("U")))
    v.put(2, 1, hotkey(v, tile("letter-n", "NEUTRE", AMBER), hk(192, 217)))
    v.put(3, 1, hotkey(v, tile("tool", "STAND", AMBER), letter("Z")))
    v.put(4, 1, hotkey(v, tile("player-skip-forward", "SKIP TOUR", AMBER), hk(8, 16777219)))
    v.put(0, 2, hotkey(v, tile("layout-dashboard", "RÉTRO", AMBER), hk(51, 51)))
    v.put(1, 2, hotkey(v, tile("dashboard", "HUD", AMBER), hk(54, 54)))
    v.put(2, 2, hotkey(v, tile("tags", "NOMS", AMBER), hk(9, 16777217)))
    v.put(3, 2, hotkey(v, tile("player-pause", "PAUSE", AMBER), letter("P")))
    v.put(4, 2, hotkey(v, tile("door-exit", "ÉCHAP", AMBER), hk(27, 16777216)))

    # aides au pilotage
    a = aids
    a.put(0, 0, back(a))
    a.put(1, 0, hotkey(a, adjust_tile("TC", True), letter("Q")))
    a.put(2, 0, hotkey(a, adjust_tile("TC", False), letter("W")))
    a.put(3, 0, hotkey(a, adjust_tile("ABS", True), letter("F")))
    a.put(4, 0, hotkey(a, adjust_tile("ABS", False), letter("V")))
    a.put(0, 1, hotkey(a, adjust_tile("TC CUT", True), letter("S")))
    a.put(1, 1, hotkey(a, adjust_tile("TC CUT", False), letter("X")))
    a.put(2, 1, hotkey(a, adjust_tile("TC SLIP", True), letter("D")))
    a.put(3, 1, hotkey(a, adjust_tile("TC SLIP", False), letter("C")))
    a.put(4, 1, hotkey(a, adjust_tile("FREIN ▲", True, CYAN), letter("G")))
    a.put(0, 2, hotkey(a, adjust_tile("FREIN ▼", False, CYAN), letter("B")))
    a.put(1, 2, hotkey(a, adjust_tile("CARTO", True), letter("J")))
    a.put(2, 2, hotkey(a, adjust_tile("CARTO", False), hk(188, 44)))
    a.put(3, 2, hotkey(a, adjust_tile("RÉGÉN", True), letter("M")))
    a.put(4, 2, hotkey(a, adjust_tile("RÉGÉN", False), hk(223, 33)))

    empty = Page("4722c796-e705-4a70-aabf-4440297ba767")   # page « par défaut » vide, comme dans les profils du logiciel
    pages = [home, menu, live, car, aids, empty]
    prof_id = "71DB85AF-2AC5-484C-88C3-4494522CC216"
    base = f"{prof_id}.sdProfile/"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(base, "")
        z.writestr(base + "manifest.json", json.dumps({
            "Device": {"Model": "20GAA9902", "UUID": DEVICE},
            "Name": "Apex Radio",
            "Pages": {"Current": str(home.id), "Default": str(empty.id), "Pages": [str(home.id)]},
            "Version": "3.0",
        }))
        z.writestr(base + "Images/", "")
        z.writestr(base + "Profiles/", "")
        for p in pages:
            d = base + f"Profiles/{str(p.id).upper()}/"
            z.writestr(d, "")
            z.writestr(d + "Images/", "")
            z.writestr(d + "manifest.json", json.dumps(p.manifest(), ensure_ascii=False))
            for name, frames in p.images.items():
                tmp = HERE / "_tmp.gif"
                save_gif(frames, tmp)
                z.write(tmp, d + "Images/" + name)
                tmp.unlink()
    # aperçus pour vérifier à l'œil
    prev = HERE / "preview"
    prev.mkdir(exist_ok=True)
    save_gif(splash_preview(keys), prev / "accueil.gif")
    print("Profil construit :", OUT, OUT.stat().st_size // 1024, "Ko")


if __name__ == "__main__":
    build()
