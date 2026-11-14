"""
Réponses de l'ingénieur aux questions du pilote (étape 3).

On repère des mots-clés dans la phrase reconnue et on répond avec les vraies
données de course. Plusieurs sujets dans la même phrase = plusieurs réponses.
"""

from __future__ import annotations

import re
import i18n
import unicodedata

from strategy import Plan
from telemetry import Snapshot
from i18n import L, dec
from phrases import pick


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", " ", t)


def _f(v: float, d: int = 1) -> str:
    return dec(f"{v:.{d}f}".replace(".0", "")) if d else f"{v:.0f}"


def _laptime(s: float | None) -> str:
    if not s:
        return L("pas encore de temps", "no time yet")
    m, r = divmod(s, 60)
    return dec(f"{int(m)} minute {r:.1f}") if m else dec(L(f"{r:.1f} secondes", f"{r:.1f} seconds"))


def _tyre_names(idx: list[int]) -> str:
    names = L("avant gauche|avant droit|arrière gauche|arrière droit", "front left|front right|rear left|rear right").split("|")
    return ", ".join(names[i] for i in idx)


# --------------------------------------------------------------------- sujets
def fuel(s: Snapshot, p: Plan) -> str:
    q = _f(s.fuel, 0)
    out = pick("a_fuel", [(f"Il te reste {q} litres.", f"You have {q} litres left."),
                          (f"{q} litres dans le réservoir.", f"{q} litres in the tank."),
                          (f"Côté essence, tu as {q} litres.", f"Fuel-wise, you've got {q} litres.")])
    if p.fuel_per_lap:
        c, n = _f(p.fuel_per_lap), _f(s.fuel / p.fuel_per_lap)
        out += " " + pick("a_fuel2", [(f"Tu consommes {c} par tour, ça fait {n} tours d'essence.",
                                       f"You're using {c} a lap, that's {n} laps of fuel."),
                                      (f"À {c} litres par tour, tu tiens {n} tours.", f"At {c} litres a lap, you can do {n} laps."),
                                      (f"Ça te laisse {n} tours, avec une conso de {c} par tour.", f"That gives you {n} laps, using {c} a lap.")])
    else:
        out += L(" J'ai besoin d'encore un ou deux tours propres pour calculer la conso.",
                 " I need one or two more clean laps to work out consumption.")
    if p.stops_needed == 0:
        out += " " + pick("a_fuel3", [("C'est bon pour aller au bout.", "That's enough to the finish."),
                                      ("Largement de quoi finir.", "Plenty to make the finish."),
                                      ("Tu es tranquille jusqu'à l'arrivée.", "You're fine all the way to the flag.")])
    if p.save_per_lap:
        out += L(f" Si tu économises {_f(p.save_per_lap)} litre par tour, on évite l'arrêt.",
                 f" Save {_f(p.save_per_lap)} litres a lap and we skip the stop.")
    return out


def energy(s: Snapshot, p: Plan) -> str:
    if s.energy is None:
        return L("Pas d'énergie virtuelle sur cette voiture, c'est l'essence qui compte.",
                 "No virtual energy on this car, fuel is what counts.")
    out = L(f"Énergie à {_f(s.energy * 100, 0)} %.", f"Energy at {_f(s.energy * 100, 0)} %.")
    if p.energy_per_lap:
        out += L(f" {_f(p.energy_per_lap * 100)} % par tour, soit {_f(s.energy / p.energy_per_lap)} tours.",
                 f" {_f(p.energy_per_lap * 100)} % a lap, so {_f(s.energy / p.energy_per_lap)} laps.")
    return out


def laps(s: Snapshot, p: Plan) -> str:
    parts = []
    if s.max_laps:
        n = max(0, s.max_laps - s.laps_done)
        parts.append(pick("a_laps", [(f"Il reste {n} tours.", f"{n} laps to go."), (f"Encore {n} tours.", f"{n} more laps."),
                                     (f"Plus que {n} tours avant l'arrivée.", f"Just {n} laps to the finish.")]))
    elif s.time_left is not None:
        m = int(s.time_left // 60)
        left = round(p.laps_to_finish) if p.laps_to_finish else None
        if s.time_left <= 0 or (left is not None and left <= 1):
            parts.append(L("C'est le dernier tour, donne tout !", "This is the last lap, give it everything!"))
        elif m < 1:
            parts.append(L(f"Moins d'une minute, encore environ {left} tours.", f"Under a minute, about {left} laps to go.") if left
                         else L("Moins d'une minute.", "Under a minute to go."))
        else:
            parts.append(L(f"Il reste {m} minute{'s' if m > 1 else ''}", f"{m} minute{'s' if m > 1 else ''} to go")
                         + (L(f", environ {left} tours.", f", about {left} laps.") if left else "."))
    if not parts:
        return L(f"Tu as bouclé {s.laps_done} tours.", f"You've done {s.laps_done} laps.")
    return " ".join(parts)


def pit(s: Snapshot, p: Plan) -> str:
    if s.session != "course":
        return L("On n'est pas en course, pas de stratégie d'arrêt pour l'instant.", "We're not racing, no pit strategy for now.")
    if not p.ready:
        return L("Je calcule encore, donne-moi un ou deux tours propres.", "Still calculating, give me one or two clean laps.")
    if p.stops_needed == 0:
        return pick("a_nopit", [("Pas besoin de rentrer, tu as de quoi finir.", "No need to pit, you can make the finish."),
                                ("Aucun arrêt prévu, on va au bout comme ça.", "No stop planned, we go to the end like this."),
                                ("On ne s'arrête plus, tu as tout ce qu'il faut.", "No more stops, you've got everything you need.")])
    if p.laps_until_box is not None and p.laps_until_box <= 1:
        when = L("Box ce tour.", "Box this lap.")
    else:
        b, n = p.box_lap, p.laps_until_box
        when = pick("a_pitwhen", [(f"Tu rentres à la fin du tour {b}, dans {n} tours.", f"You pit at the end of lap {b}, in {n} laps."),
                                  (f"Box dans {n} tours, à la fin du tour {b}.", f"Box in {n} laps, end of lap {b}."),
                                  (f"On t'attend au stand dans {n} tours, tour {b}.", f"We'll see you in the pits in {n} laps, lap {b}.")])
    serv = []
    if p.fuel_to_add is not None:
        serv.append(L(f"{_f(p.fuel_to_add, 0)} litres", f"{_f(p.fuel_to_add, 0)} litres of fuel"))
    if p.energy_target is not None:
        serv.append(L(f"énergie à {_f(p.energy_target * 100, 0)} %", f"energy to {_f(p.energy_target * 100, 0)} %"))
    if p.tyre_compound == "pluie":
        serv.append(L("pneus pluie", "wet tyres"))
    elif p.tyre_compound == "slicks":
        serv.append(L("retour en slicks", "back to slicks"))
    elif p.change_tyres:
        serv.append(L("4 pneus neufs", "four new tyres"))
    elif p.change_tyres is False:
        serv.append(L("on garde les pneus", "we keep the tyres"))
    extra = L(f" Il faudra {p.stops_needed} arrêts au total.", f" {p.stops_needed} stops in total.") if p.stops_needed and p.stops_needed > 1 else ""
    return (L(f"{when} On met {', '.join(serv)}.", f"{when} {', '.join(serv)}.") + extra) if serv else when + extra


COLD_TYRE = 55.0   # °C : en dessous, les pneus sont vraiment froids


def tyres(s: Snapshot, p: Plan) -> str:
    out = []
    flats = [i for i, f in enumerate(getattr(s, "flat", []) or []) if f]
    if flats:
        out.append(L(f"Crevaison {_tyre_names(flats)} ! Rentre au stand doucement.", f"Puncture {_tyre_names(flats)}! Bring it in slowly."))
    wear = [w * 100 for w in s.tyre_wear]          # LMU : 100 % = pneu neuf
    if any(wear):
        avg = sum(wear) / 4
        worst = min(range(4), key=lambda i: wear[i])
        state = (L("Ils sont comme neufs", "They're like new") if avg >= 95 else
                 L("Ils sont en bon état", "They're in good shape") if avg >= 80 else
                 L("Ils commencent à s'user", "They're starting to wear") if avg >= 60 else
                 L("Ils sont bien usés", "They're well worn") if avg >= 40 else
                 L("Ils sont très usés, pense à les changer", "They're very worn, think about changing them"))
        out.append(L(f"{state} : il reste {_f(avg, 0)} % de gomme en moyenne, le plus usé c'est l'{_tyre_names([worst])} à {_f(wear[worst], 0)} %.",
                     f"{state}: {_f(avg, 0)} % of rubber left on average, the most worn is the {_tyre_names([worst])} at {_f(wear[worst], 0)} %."))
    if p.tyre_laps_left is not None:
        out.append(L(f"Encore environ {_f(p.tyre_laps_left, 0)} tours avant qu'ils soient vraiment usés.",
                     f"About {_f(p.tyre_laps_left, 0)} more laps before they're really worn."))
    temps = [x for x in (s.tyre_temp or []) if x and x > -50]
    opt = getattr(s, "tyre_opt", None)
    if len(temps) == 4:
        avg_t = sum(temps) / 4
        if opt:
            # la « température idéale » de LMU (~90 °C) n'est pas atteinte en roulage normal (69 °C en GT3,
            # comme dans le jeu) : on ne parle de pneus froids que s'ils le sont vraiment
            if avg_t < COLD_TYRE:
                out.append(L(f"Ils sont encore froids : {_f(avg_t, 0)} degrés.", f"They're still cold: {_f(avg_t, 0)} degrees."))
            elif avg_t > opt + 15:
                out.append(L(f"Ils sont trop chauds : {_f(avg_t, 0)} degrés, l'idéal est vers {_f(opt, 0)}. Ménage-les un peu.",
                             f"They're too hot: {_f(avg_t, 0)} degrees, ideal is around {_f(opt, 0)}. Look after them a bit."))
            else:
                out.append(L(f"Bonne température, {_f(avg_t, 0)} degrés.", f"Good temperature, {_f(avg_t, 0)} degrees."))
        else:
            out.append(L(f"Températures autour de {_f(avg_t, 0)} degrés.", f"Temperatures around {_f(avg_t, 0)} degrees."))
        front, rear = (temps[0] + temps[1]) / 2, (temps[2] + temps[3]) / 2
        if abs(front - rear) > 12:
            hot = L("l'avant", "the fronts") if front > rear else L("l'arrière", "the rears")
            out.append(L(f"{hot.capitalize()} chauffe plus, de {_f(abs(front - rear), 0)} degrés.",
                         f"{hot.capitalize()} {'are' if True else 'is'} running {_f(abs(front - rear), 0)} degrees hotter."))
    if not out:
        return L("Je n'arrive pas à lire tes pneus pour l'instant.", "I can't read your tyres right now.")
    return " ".join(out)


def _sec(g: float) -> str:
    return L(f"{_f(g)} seconde{'s' if g >= 2 else ''}", f"{_f(g)} second{'s' if g != 1 else ''}")


def gaps(s: Snapshot, p: Plan) -> str:
    # écart dans ta catégorie d'abord (celui de LMU est souvent vide), sinon l'écart général
    ga = s.gap_class_ahead if s.gap_class_ahead is not None else s.gap_ahead
    gb = s.gap_class_behind if s.gap_class_behind is not None else s.gap_behind
    t = LAST_TEXT
    front = bool(re.search(r"devant|ahead|in front|attaque|premier|leader|tete", t))
    back = bool(re.search(r"derriere|behind|revient|catching|suit", t))
    leader = s.ahead is None and (s.class_position or s.position) == 1
    # « il revient / il remonte / je reprends du temps ? » : on répond avec l'évolution de l'écart
    if re.search(r"remont|revien|rapproch|mont(e|ent|ant)? fort|fond(s)? sur|reprend|recoll|s eloign|echapp|lache|creuse|catching|closing|pulling", t):
        try:
            from alerts import GapTrend, _dix
            tr = GapTrend.LAST
        except Exception:
            tr = None
        side = "behind" if (back and not front) or (not front and re.search(r"remont|revien|rapproch|mont", t)) else "ahead"
        r = tr.trend(side) if tr else None
        if r:
            rate, gap, place = r
            who = f"P{place}" if place else L("la voiture", "the car")
            if side == "behind":
                if rate < -0.05:
                    n = int(gap / -rate) + 1
                    return L(f"Oui, {who} revient de {_dix(rate)} par tour. Il est à {_sec(gap)}, sur toi dans {n} tour{'s' if n > 1 else ''} à ce rythme.",
                             f"Yes, {who} is closing by {_dix(rate)} a lap. He's {_sec(gap)} back, on you in {n} lap{'s' if n > 1 else ''} at this pace.")
                if rate > 0.05:
                    return L(f"Non, tu creuses : tu prends {_dix(rate)} par tour à {who}, il est à {_sec(gap)}.",
                             f"No, you're pulling away: {_dix(rate)} a lap on {who}, he's {_sec(gap)} back.")
                return L(f"L'écart est stable avec {who}, à {_sec(gap)}.", f"The gap to {who} is stable, {_sec(gap)}.")
            if rate < -0.05:
                n = int(gap / -rate) + 1
                return L(f"Oui, tu reprends {_dix(rate)} par tour à {who}. Il est à {_sec(gap)}, dans ses roues dans {n} tour{'s' if n > 1 else ''}.",
                         f"Yes, you're gaining {_dix(rate)} a lap on {who}. He's {_sec(gap)} ahead, on his gearbox in {n} lap{'s' if n > 1 else ''}.")
            if rate > 0.05:
                return L(f"Non, {who} s'éloigne de {_dix(rate)} par tour, il est à {_sec(gap)}.",
                         f"No, {who} is pulling away by {_dix(rate)} a lap, {_sec(gap)} ahead.")
            return L(f"L'écart est stable avec {who}, à {_sec(gap)}.", f"The gap to {who} is stable, {_sec(gap)}.")
    if front and not back:
        if ga is not None:
            return L(f"La voiture devant est à {_sec(ga)}.", f"The car ahead is {_sec(ga)} up the road.")
        if leader:
            return L("Tu es en tête, il n'y a personne devant toi.", "You're leading, there's nobody ahead.")
        return L("Je n'arrive pas à lire l'écart avec la voiture devant pour l'instant.", "I can't read the gap to the car ahead right now.")
    if back and not front:
        if gb is not None:
            return L(f"La voiture derrière est à {_sec(gb)}.", f"The car behind is {_sec(gb)} back.")
        return L("Personne derrière toi pour l'instant.", "Nobody behind you right now.")
    parts = []
    if ga is not None:
        parts.append(L(f"{_sec(ga)} devant", f"{_sec(ga)} ahead"))
    elif leader:
        parts.append(L("tu es en tête", "you're leading"))
    if gb is not None:
        parts.append(L(f"{_sec(gb)} derrière", f"{_sec(gb)} behind"))
    if not parts:
        return L("Personne de proche autour de toi.", "Nobody close around you.")
    return L("Écart : ", "Gaps: ") + ", ".join(parts) + "."


def repairs(s: Snapshot, p: Plan) -> str:
    if s.no_repair:
        return L("Tu m'as demandé de ne pas réparer : au prochain arrêt, on ne touche pas à la voiture.",
                 "You asked for no repairs: we won't touch the car at the next stop.")
    if s.repair:
        return L("Oui, la voiture est abîmée : je prévois les réparations au prochain arrêt. Dis « pas de réparation » si tu n'en veux pas.",
                 "Yes, the car is damaged: I'm planning repairs at the next stop. Say \"no repairs\" if you don't want them.")
    return pick("a_norep", [("Pas de dégâts importants, pas besoin de réparer.", "No significant damage, no need for repairs."),
                            ("La voiture va bien, rien à réparer.", "The car looks fine, nothing to fix."),
                            ("Je ne vois pas de dégâts sérieux, on ne répare pas.", "No serious damage on my side, no repairs needed.")])


def position(s: Snapshot, p: Plan) -> str:
    out = pick("a_pos", [(f"Tu es P{s.position}", f"You're P{s.position}"), (f"Tu roules P{s.position}", f"You're running P{s.position}"),
                         (f"Position : P{s.position}", f"Position: P{s.position}")])
    if s.class_position and s.class_position != s.position:
        out += L(f", P{s.class_position} dans ta catégorie", f", P{s.class_position} in class")
    return out + "."


def _forecast_text(fc: list, now: float, total: float | None, label: str) -> str:
    """Résumé des prévisions : pluie prévue (quand, combien) ou temps sec."""
    try:
        from alerts import SKY_FR, SKY_EN
    except Exception:
        SKY_FR = SKY_EN = []
    ahead = [n for n in fc if n["at"] >= now - 0.01]
    if not ahead:
        return ""
    wet = [n for n in ahead if n["rain"] >= 0.3]
    if not wet:
        return L(f"{label} : pas de pluie prévue.", f"{label}: no rain expected.")
    n = max(wet, key=lambda x: x["rain"])
    sky = (SKY_FR if not i18n.en() else SKY_EN)[n["sky"]] if 0 <= n["sky"] < len(SKY_FR) else ""
    when = ""
    if total:
        mins = (n["at"] - now) * total / 60
        when = (L(" maintenant", " now") if mins < 2 else L(f" dans environ {int(mins)} minutes", f" in about {int(mins)} minutes"))
    else:
        when = L([" au départ", " au premier quart", " à mi-séance", " au troisième quart", " vers la fin"][min(4, round(n['at'] * 4))],
                 [" at the start", " at the first quarter", " at half distance", " at the third quarter", " near the end"][min(4, round(n['at'] * 4))])
    return L(f"{label} : risque de pluie {_f(n['rain'] * 100, 0)} %{when}{', ' + sky if sky else ''}.",
             f"{label}: {_f(n['rain'] * 100, 0)} % chance of rain{when}{', ' + sky if sky else ''}.")


def forecast_answer(t: str, s: Snapshot) -> str:
    """« Il va pleuvoir ? », « la météo pour la course ? », « c'est pour les qualifs ou la course ? »."""
    try:
        from alerts import Weather
    except Exception:
        return ""
    parts = []
    want_q = re.search(r"qualif|calif|kalif|qualy|qualifying", t)
    want_r = re.search(r"\bcourse\b|\brace\b", t)
    cur = Weather.LAST.forecast if Weather.LAST else []
    if cur and not (want_q or want_r):
        total = (s.elapsed + s.time_left) if s.time_left else None
        now = s.elapsed / total if total else 0.0
        parts.append(_forecast_text(cur, now, total, L("Pour cette séance", "This session")))
    if want_q:
        parts.append(_forecast_text(Weather.session_forecast("QUALIFY"), 0.0, None, L("Pour les qualifs", "Qualifying")))
    if want_r or (not parts and not want_q):
        parts.append(_forecast_text(Weather.session_forecast("RACE"), 0.0, None, L("Pour la course", "The race")))
    return " ".join(x for x in parts if x)


def weather(s: Snapshot, p: Plan) -> str:
    out = L(f"{p.weather or 'Sec'}. Air {_f(s.air_temp, 0)} degrés, piste {_f(s.track_temp, 0)}.",
            f"{p.weather or 'Dry'}. Air {_f(s.air_temp, 0)} degrees, track {_f(s.track_temp, 0)}.")
    if re.search(r"pleuv|pluie|prevu|prevision|va (faire|y avoir)|course|qualif|calif|tout a l heure|plus tard|forecast|later|rain|qualy", LAST_TEXT):
        fc = forecast_answer(LAST_TEXT, s)
        if fc:
            out += " " + fc
    if p.tyre_compound == "pluie":
        out += L(" Je te conseille les pneus pluie au prochain arrêt.", " I'd go to wets at the next stop.")
    elif p.tyre_compound == "slicks":
        out += L(" On peut repasser en slicks.", " We can go back to slicks.")
    return out


def laptimes(s: Snapshot, p: Plan) -> str:
    return L(f"Dernier tour en {_laptime(s.last_lap)}, meilleur en {_laptime(s.best_lap)}.",
             f"Last lap {_laptime(s.last_lap)}, best {_laptime(s.best_lap)}.")


def status(s: Snapshot, p: Plan) -> str:
    return " ".join([position(s, p), laps(s, p), pit(s, p)])


TOPICS = [
    # (mots-clés, fonction)
    (r"essence|des sens|d sens|carbu|fuel|conso|litre|reservoir|jus|gasoil|\bgas\b|petrol|consumption|\btank", fuel),
    (r"energie|batterie|virtuel|energy|battery|virtual", energy),
    (r"stand|\bbox|arret|rentr|\bpit|ravitaill|strateg|\bstop\b|come in", pit),
    (r"pneu|pner|peneu|pneumatique|gomme|usure|pression|crev|\betat d(u|e|es)\b(?!.*(voiture|caisse|carrosserie|course|jeu de la))|\btyre|\btire|rubber|\bwear|\bpressure", tyres),
    (r"ecart|devant|derriere|\bgap|attaque|revient|remont|rapproch|monte fort|montant fort|ahead|behind|in front|catching|closing", gaps),
    (r"repar|degat|degare|dommage|abime|casse|etat de (la|ma) (voiture|caisse|bagnole)|damage|repair", repairs),
    (r"position|place|classement|placement|cassement|quelle p\b|combien ?t?i?eme|combien siam|combien.*(je suis|suis je)|je suis ou\b|where am i|what p\b", position),
    (r"meteo|pluie|pleut|pleuvoir|mouill|humid|sec\b|temperature (de la piste|piste|de l air|exterieur)|nuage|quel temps|temps qu il fait|temps il fait|sous la pluie|a la pluie|qualif|calif|weather|\brain|\bwet\b|\bdry\b|cloud", weather),
    (r"chrono|dernier tour|meilleur tour|temps au tour|mon tour|rythme|tourne en|je tourne|lap time|last lap|best lap|\bpace\b", laptimes),
    (r"combien de tour|tours restant|reste.*tour|temps restant|reste.*minute|reste combien de temps|combien de temps.*reste|\bfin\b|arrivee|damier|how many laps|laps (left|to go|remaining)|time (left|remaining)|finish", laps),
    (r"point complet|fais (moi )?le point|\ble point\b|situation|resume|tout va|comment ca va|ca donne quoi|ca se passe|recap|update|summary|how are we|status|how s it going", status),
]


LAPTIMES = None  # branché par app.py
BEHAVIOR = None
PIT_ACTION = None   # fonction appelée pour régler le menu des stands
REPAIR_SET = None   # fonction(True/False) : réparer ou pas au prochain arrêt ; renvoie True si le menu est re-réglé
LAST_TEXT = ""      # dernière question (normalisée), pour savoir si on parle de devant ou de derrière


def pit_command(s: Snapshot, p: Plan) -> str:
    if PIT_ACTION is None:
        return L("Je ne peux pas régler le stand pour l'instant.", "I can't set the pit menu right now.")
    PIT_ACTION()
    return L("Je règle le menu des stands.", "Setting up the pit menu.")


def behavior(s: Snapshot, p: Plan) -> str:
    return BEHAVIOR.summary() if BEHAVIOR else L("Analyse du comportement indisponible.", "Handling analysis unavailable.")


def record(s: Snapshot, p: Plan) -> str:
    return LAPTIMES.record_text(s) if LAPTIMES else L("Pas de chronos enregistrés.", "No lap times recorded.")


def sectors(s: Snapshot, p: Plan) -> str:
    if not LAPTIMES or not LAPTIMES.last:
        return L("Il me faut un tour complet et valide pour comparer les secteurs.", "I need a full valid lap to compare sectors.")
    t = LAPTIMES.summary()
    return t or L("Pas de voiture à comparer autour de toi pour l'instant.", "No car to compare with around you yet.")


def sectors_ahead(s: Snapshot, p: Plan) -> str:
    t = LAPTIMES.summary("ahead") if LAPTIMES else ""
    return t or L("Pas de comparaison possible avec la voiture devant pour l'instant.", "Can't compare with the car ahead yet.")


def sectors_behind(s: Snapshot, p: Plan) -> str:
    t = LAPTIMES.summary("behind") if LAPTIMES else ""
    return t or L("Pas de comparaison possible avec la voiture derrière pour l'instant.", "Can't compare with the car behind yet.")


def penalty(s: Snapshot, p: Plan) -> str:
    if not s.penalties:
        return L("Aucune pénalité en cours.", "No penalty pending.")
    return L(f"Tu as {s.penalties} pénalité{'s' if s.penalties > 1 else ''} à purger aux stands. Regarde l'écran pour le type.",
             f"You have {s.penalties} penalt{'ies' if s.penalties > 1 else 'y'} to serve in the pits. Check the screen for the type.")


TOPICS[:0] = [
    (r"penalit|drive through|stop (and|n|et) go|penalty", penalty),
    (r"(prepare|regle|regule|mets|programme|set up|setup the|program).*(stand|arret|box|menu|pit|stop)|(stand|arret).*(prepare|regle)|prepare (moi )?(l arret|tout|la re)|je rentre (ce tour|au stand|maintenant|ce tout)|box this lap|i m pitting|pitting this lap", pit_command),
    (r"comporte|sous vir|sousvir|survir|equilibr|reglage|setup|conseil|satope|sur virage|plus vite|ameliorer|progresser|glisse|bloqu|patin|tient pas|braqu|tourne pas|ralenti|pousse|lourde|decroche|chasse|instable|nerveuse|freinage|\bje freine\b|freine (trop|tot|tard)|balance|understeer|oversteer|handling|advice|sliding|locking|wheelspin|loose|snap|braking|won t turn", behavior),
    (r"record|meilleur temps (ici|du circuit)|tour ideal|personal best|ideal lap", record),
    (r"(secteur|perd|gagne|reprend|compar|plus rapide|plus lent|sector|losing|gaining|faster|slower).*(devant|ahead|in front)|(devant|ahead|in front).*(secteur|perd|gagne|rapide|lent|sector|losing|gaining|faster|slower)", sectors_ahead),
    (r"(secteur|perd|gagne|reprend|compar|plus rapide|plus lent|sector|losing|gaining|faster|slower).*(derriere|behind)|(derriere|behind).*(secteur|perd|gagne|rapide|lent|sector|losing|gaining|faster|slower)", sectors_behind),
    (r"secteur|ou je perds?|ou je gagne|perds? du temps|compar|sector|where am i losing|where do i lose", sectors),
]


# ------------------------------------------------------------------ nouvelles questions (1.2.13)
def _last_name(d) -> str:
    return ((d or {}).get("name") or "").split(" ")[-1]


def brakes(s: Snapshot, p: Plan) -> str:
    bt = [b for b in (s.brake_temp or []) if b and b > 0]
    if len(bt) < 4:
        return L("Je n'ai pas la température des freins.", "No brake temperature data.")
    carbon = any(k in (s.car_class or "") for k in ("Hypercar", "LMP2"))
    cold, hot = (250, 1000) if carbon else (150, 750)
    front, rear = (bt[0] + bt[1]) / 2, (bt[2] + bt[3]) / 2
    txt = L(f"Freins à {front:.0f} degrés devant et {rear:.0f} derrière.",
            f"Brakes at {front:.0f} degrees front and {rear:.0f} rear.")
    m = max(bt)
    if m > hot:
        i = bt.index(m)
        txt += " " + L(f"L'{_tyre_names([i])} chauffe beaucoup, ménage les gros freinages ou ouvre les écopes.",
                       f"The {_tyre_names([i])} is very hot, ease the big stops or open the ducts.")
    elif max(front, rear) < cold:
        txt += " " + L("Ils sont froids, appuie fort sur les premiers freinages.", "They're cold, brake hard to warm them.")
    else:
        txt += " " + L("C'est dans la bonne fenêtre.", "That's in the window.")
    return txt


def track_limits(s: Snapshot, p: Plan) -> str:
    if not s.tl_per_penalty:
        return L(f"{s.tl_steps} avertissement{'s' if s.tl_steps > 1 else ''} pour limites de piste."
                 if s.tl_steps else "Aucun avertissement pour limites de piste.",
                 f"{s.tl_steps} track limit warning{'s' if s.tl_steps != 1 else ''}." if s.tl_steps else "No track limit warnings.")
    left = s.tl_per_penalty - s.tl_steps
    txt = L(f"Limites de piste : {s.tl_steps} avertissement{'s' if s.tl_steps > 1 else ''} sur {s.tl_per_penalty}.",
            f"Track limits: {s.tl_steps} warning{'s' if s.tl_steps != 1 else ''} of {s.tl_per_penalty}.")
    if 0 < left <= 1:
        txt += " " + L("Encore un et c'est la pénalité, reste bien dans les lignes.", "One more and it's a penalty, stay inside the lines.")
    return txt


def lap_valid(s: Snapshot, p: Plan) -> str:
    if s.lap_invalid:
        return L("Ce tour est invalidé, il ne comptera pas.", "This lap is invalidated, it won't count.")
    return L("Pour l'instant ton tour est valide.", "Your lap is valid so far.")


def leader(s: Snapshot, p: Plan) -> str:
    me = s.class_position or s.position
    if me == 1:
        b = s.behind
        tail = (L(f" {_last_name(b)} est à {_sec(s.gap_class_behind)}.", f" {_last_name(b)} is {_sec(s.gap_class_behind)} back.")
                if b and s.gap_class_behind else "")
        return L("C'est toi qui mènes ta catégorie !", "You're leading your class!") + tail
    lead = next((r for r in s.rivals if r.get("cpos") == 1), None)
    if not lead:
        return L("Je ne vois pas encore le leader de ta catégorie.", "I can't see your class leader yet.")
    name = _last_name(lead) or L("le leader", "the leader")
    g = lead.get("gap")
    if lead.get("in_pits"):
        return L(f"Le leader, {name}, est aux stands. Tu es P{me}.", f"The leader, {name}, is in the pits. You're P{me}.")
    if g is None:
        return L(f"Le leader de ta catégorie, c'est {name}, il a au moins un tour d'avance. Tu es P{me}.",
                 f"Your class leader is {name}, at least a lap ahead. You're P{me}.")
    return L(f"Le leader de ta catégorie, c'est {name}, {_sec(abs(g))} devant toi. Tu es P{me}.",
             f"Your class leader is {name}, {_sec(abs(g))} ahead. You're P{me}.")


def _who_line(car, gap, ahead: bool) -> str:
    if not car:
        return (L("Personne devant toi dans ta catégorie, tu es en tête !", "Nobody ahead in your class, you're leading!") if ahead
                else L("Personne derrière toi dans ta catégorie.", "Nobody behind you in your class."))
    name = _last_name(car) or L("un pilote", "a driver")
    where = L("devant", "ahead") if ahead else L("derrière", "behind")
    txt = L(f"{where.capitalize()}, c'est {name}", f"{where.capitalize()} is {name}")
    if car.get("car"):
        txt += L(f", en {car['car']}", f", in the {car['car']}")
    if car.get("in_pits"):
        return txt + L(", il est aux stands.", ", he's in the pits.")
    if gap:
        txt += L(f", à {_sec(gap)}", f", {_sec(gap)} away")
    return txt + "."


def who_ahead(s: Snapshot, p: Plan) -> str:
    return _who_line(s.ahead, s.gap_class_ahead, True)


def who_behind(s: Snapshot, p: Plan) -> str:
    return _who_line(s.behind, s.gap_class_behind, False)


def stops_count(s: Snapshot, p: Plan) -> str:
    n = s.pit_stops
    if not n:
        return L("Tu n'as pas encore fait d'arrêt.", "You haven't pitted yet.")
    return L(f"Tu as fait {n} arrêt{'s' if n > 1 else ''}.", f"You've made {n} stop{'s' if n > 1 else ''}.")


def flags(s: Snapshot, p: Plan) -> str:
    if s.game_phase == 6:
        return L("Neutralisation en cours, safety car ou full course yellow. Pas de dépassement, respecte la vitesse.",
                 "Neutralisation, safety car or full course yellow. No overtaking, watch your speed.")
    if s.game_phase == 7:
        return L("La course est arrêtée, drapeau rouge.", "The race is stopped, red flag.")
    if s.game_phase == 8:
        return L("Drapeau à damier, c'est le dernier tour pour toi.", "Chequered flag is out, last lap for you.")
    if s.yellow:
        return L("Drapeau jaune sur la piste, prudence et pas de dépassement dans la zone.",
                 "Yellow flag on track, careful and no overtaking in the zone.")
    return L("Piste libre, drapeau vert.", "Track is clear, green flag.")


def field_size(s: Snapshot, p: Plan) -> str:
    cls = len(s.rivals) + 1 if s.rivals else 0
    if cls and s.num_cars and s.num_cars > cls:
        return L(f"{cls} voitures dans ta catégorie, {s.num_cars} en tout.", f"{cls} cars in your class, {s.num_cars} overall.")
    if s.num_cars:
        return L(f"{s.num_cars} voitures en piste.", f"{s.num_cars} cars on track.")
    return L("Je ne vois pas encore les autres voitures.", "I can't see the other cars yet.")


def pace_rank(s: Snapshot, p: Plan) -> str:
    mine = s.best_lap
    others = [(r.get("best"), r) for r in s.rivals if r.get("best")]
    if not mine or not others:
        return L("Il me faut un tour chrono de toi et des autres pour comparer.", "I need lap times from you and the others to compare.")
    rank = 1 + sum(1 for b, _ in others if b < mine)
    best, who = min(others, key=lambda x: x[0])
    total = len(others) + 1
    if rank == 1:
        return L(f"Tu as le meilleur tour de ta catégorie, {_laptime(mine)}. Le plus proche est à {_f(best - mine, 1 if best - mine >= 0.1 else 2)} seconde.",
                 f"You have the fastest lap in your class, {_laptime(mine)}. Next best is {_f(best - mine, 1 if best - mine >= 0.1 else 2)} s slower.")
    return L(f"Ton meilleur tour est le {rank}e sur {total} de ta catégorie. Le plus rapide, c'est {_last_name(who)} en {_laptime(best)}, "
             f"{_f(mine - best, 1 if mine - best >= 0.1 else 2)} seconde devant toi.",
             f"Your best lap ranks {rank} of {total} in class. Fastest is {_last_name(who)} with {_laptime(best)}, "
             f"{_f(mine - best, 1 if mine - best >= 0.1 else 2)} s quicker.")


TOPICS[:0] = [
    (r"\bfreins?\b(?! a main)|\bdisques? de frein|\bbrakes?\b", brakes),
    (r"limites? de (la )?piste|avertissements?|track limits?|\bwarnings?\b", track_limits),
    (r"(mon |ce |le )?(tour|chrono) (est |il est )?(valide|invalide|compte)|tour valid|valid lap|lap (valid|invalid|count)", lap_valid),
    (r"\bleader\b|qui (mene|est premier|est en tete|gagne)|en tete de|premier de (la |ma )?(categorie|classe)|ecart (avec|sur|au) (le )?(premier|leader)|who s leading|class leader", leader),
    (r"(c est )?qui (est |c est )?devant|who s (ahead|in front)|who is (ahead|in front)", who_ahead),
    (r"(c est )?qui (est |c est )?derriere|who s behind|who is behind", who_behind),
    (r"combien d arrets|nombre d arrets|(arrets|arret) (j ai|deja) fait|how many (stops|pit stops)", stops_count),
    (r"safety|voiture de securite|neutralis|full course|\bfcy\b|drapeau(?! a damier)|pourquoi (jaune|rouge)|\bflags?\b|yellow", flags),
    (r"combien (de |d )(voitures|pilotes|concurrents|adversaires)|how many (cars|drivers)", field_size),
    (r"(suis je|je suis) (rapide|lent|dans le rythme)|mon rythme (par rapport|face)|meilleur tour de (la course|la categorie|ma categorie)|plus rapide de (la course|la categorie)|fastest lap|am i (fast|quick|slow)", pace_rank),
]


VOICE = None      # pour le mode silence
ENG = None        # pour répéter le dernier message

COMMANDS = [
    (r"\bsilence\b|tais toi|taise|chut\b|moins de message|arrete de parler|mode calme|plus que l urgent|be quiet|shut up|quiet mode|less talk|only urgent", "quiet"),
    (r"reparle|repale|reparler|parle a nouveau|tu peux parler|fin du silence|toutes les infos|remets? (la radio|les annonces)|talk again|you can talk|all info|unmute|resume radio", "talk"),
    (r"repete|repeter|redis|redire|j ai pas (compris|entendu)|pardon\b|t as dit quoi|qu est ce que tu as dit|repeat|say again|come again|what did you say", "repeat"),
]


def command(text: str) -> str | None:
    """Commandes de radio (silence, reparle, répète) : marchent même hors de la voiture."""
    t = _norm(text)
    for pattern, cmd in COMMANDS:
        if not re.search(pattern, t):
            continue
        if cmd == "quiet" and VOICE is not None:
            VOICE.quiet = True
            return L("Bien reçu, je ne te dis plus que l'urgent. Dis « reparle » pour tout réentendre.",
                     "Copy, urgent calls only from now on. Say \"talk again\" to hear everything.")
        if cmd == "talk" and VOICE is not None:
            VOICE.quiet = False
            return L("C'est noté, je te redonne toutes les infos.", "Copy, back to full info.")
        if cmd == "repeat" and ENG is not None:
            last = next((m["text"] for m in ENG.radio if not m.get("me")), None)
            return L(f"Je répète : {last}", f"I repeat: {last}") if last else L("Je n'ai encore rien dit.", "I haven't said anything yet.")
    return None


# ------------------------------------------------------------ discussion
# Petites phrases de radio qui marchent partout, même hors de la voiture.
def _radio_check(s: Snapshot) -> str:
    return pick("a_check", [("Oui, je t'entends, cinq sur cinq.", "Yes, I hear you loud and clear."),
                            ("Cinq sur cinq, je te reçois parfaitement.", "Five by five, reading you perfectly."),
                            ("Reçu fort et clair.", "Loud and clear.")])


def _here(s: Snapshot) -> str:
    return pick("a_here", [("Je suis là, je t'écoute.", "I'm here, go ahead."), ("Toujours là, vas-y.", "Still here, go ahead."),
                           ("Présent, je t'écoute.", "Here, listening.")])


def _hello(s: Snapshot) -> str:
    import voice
    return L(f"Salut ! Je suis là, {'prête' if voice.engineer_female() else 'prêt'} quand tu veux.", "Hi! I'm here, ready when you are.")


def _thanks(s: Snapshot) -> str:
    return pick("a_thanks", [("Avec plaisir.", "You're welcome."), ("De rien, c'est mon boulot.", "No problem, that's my job."),
                             ("Pas de quoi, on fait équipe.", "Anytime, we're a team.")])


def _who(s: Snapshot) -> str:
    import voice
    name = voice.engineer_name()
    return L(f"Je suis {name}, ton {'ingénieure' if voice.engineer_female() else 'ingénieur'} de course.",
             f"I'm {name}, your race engineer.")


def _help(s: Snapshot) -> str:
    return L("Demande-moi l'essence, l'énergie, les pneus, le stand, les écarts, ta position, la météo, tes chronos, "
             "tes secteurs ou le comportement de la voiture. Je peux aussi régler le menu des stands.",
             "Ask me about fuel, energy, tyres, pit stop, gaps, position, weather, lap times, sectors "
             "or car handling. I can also set up the pit menu.")


def _time(s: Snapshot) -> str:
    import datetime
    n = datetime.datetime.now()
    h = "heure" if n.hour <= 1 else "heures"
    return L(f"Il est {n.hour} {h} {n.minute:02d}." if n.minute else f"Il est {n.hour} {h}.", f"It's {n:%H:%M}.")


def _how_are_you(s: Snapshot) -> str | None:
    if s.on_track:   # en piste, « ça va ? » = le point complet (sujet status)
        return None
    import voice
    return L(f"Ça va très bien, merci ! {'Prête' if voice.engineer_female() else 'Prêt'} pour la course.", "All good, thanks! Ready for the race.")


def _car(s: Snapshot) -> str:
    from alerts import car_sentence
    return car_sentence(s.car_class, s.car)


def _joke(s: Snapshot) -> str:
    return L("Les blagues, c'est après le drapeau à damier. Reste concentré !",
             "Jokes are for after the chequered flag. Stay focused!")


CHAT = [
    (r"\bm entends?\b|\bm entendez\b|\bm as t en\b|\bm attends\b|\bmentend|tu m en tends|tu me recois|me recois tu|tu recois|radio check|test radio|\ballo\b|"
     r"can you hear|do you hear|hear me|do you copy|you copy", _radio_check),
    (r"\b(t es|tu es|es tu|t es bien) la\b|t es toujours la|\b(tu es|t es|es tu) (pret|prete)s?\b|on y va\b|you there|are you there|are you ready|ready\b", _here),
    (r"^(bonjour|salut|hello|coucou|hey|bonsoir|hi)\b", _hello),
    (r"\bmerci\b|thank", _thanks),
    (r"qui es tu|t es qui|tu es qui|comment tu t appelles|ton nom|ton prenom|who are you|your name", _who),
    (r"que (peux|sais) tu|qu est ce que tu (peux|sais)|sais faire|tu peux faire quoi|tu fais quoi|\baide\b|\bhelp\b|what can you", _help),
    (r"quelle heure|l heure qu il|what time", _time),
    (r"\bca va\b|comment vas tu|how are you", _how_are_you),
    (r"blague|joke|funny", _joke),
    (r"\belms\b|\be l m s\b|\belm\b|\bwec\b|\bw e c\b|\bwc\b|quelle voiture|quelle categorie|quel championnat|"
     r"which car|what car|which class|which championship", _car),
]


FILLER = (_hello, _thanks)   # « salut », « merci » : seulement si la phrase ne demande rien d'autre


def chat(t: str, s: Snapshot, alone: bool = True) -> list[str]:
    """alone=False : la phrase demande aussi des données, on saute « salut » / « merci »."""
    out = []
    for pattern, fn in CHAT:
        if re.search(pattern, t) and (alone or fn not in FILLER):
            r = fn(s)
            if r and r not in out:
                out.append(r)
    return out


# la négation doit porter sur la réparation elle-même (« pas de réparation »), pas sur un autre mot
# de la phrase (« réparation sans ravitaillement » = on répare !)
NO_REPAIR = (r"\b(pas|plus|sans|aucune?) (besoin )?(de |d |la |les |des )?repar|"
             r"\b(annule|annuler|enleve|enlever|retire|retirer|supprime|supprimer|oublie|leve|lever) (les |la |des )?repar|"
             r"\bne (le |la |les )?repar\w* (pas|rien)|\brepar\w* non\b|\bne repare pas|"
             r"don t (fix|repair)|no repairs?\b|skip (the )?repairs?|cancel (the )?repairs?|"
             r"\b(remove|no) (the )?(repairs?|damage)")
DO_REPAIR = (r"\b(repare|reparer|reparez|reparation|reparations|reparte)\b|\brepart (tout|juste|la carrosserie|seulement)|\bfix (the )?(car|damage)|\brepair")


def repair_command(t: str) -> str | None:
    """« pas de réparation » / « répare la voiture » : change le menu des stands."""
    if re.search(r"^(il faut|faut il|est ce qu|on doit|je dois|tu crois|ca vaut)", t):
        return None   # c'est une question (« il faut réparer ? »), pas un ordre
    if re.search(NO_REPAIR, t):
        want = False
    elif re.search(DO_REPAIR, t) and re.search(r"\b(repare|reparer|reparez|reparte|repart|tout|toutes|carrosserie|fix|repair the|do the|on repare)\b|"
                                            r"\b(pour|juste|seulement|avec) (la |les |une |des )?repar", t):
        want = True
    else:
        return None
    if REPAIR_SET is None:
        return L("Je ne peux pas changer les réparations pour l'instant.", "I can't change the repairs right now.")
    body_only = want and bool(re.search(r"carrosserie|body|aero", t)) and not re.search(r"\btout\b|\ball\b|full", t)
    menu = REPAIR_SET(want, not body_only)
    if not want:
        out = L("C'est noté, on ne répare pas au prochain arrêt.", "Copy, no repairs at the next stop.")
    elif body_only:
        out = L("C'est noté, on répare seulement la carrosserie au prochain arrêt.", "Copy, bodywork only at the next stop.")
    else:
        out = L("C'est noté, on répare tout au prochain arrêt.", "Copy, full repairs at the next stop.")
    if menu:
        out += L(" Je corrige le menu des stands.", " Updating the pit menu.")
    return out


NO_FUEL = (r"\b(pas|sans|aucun|zero|0) (de |d |du )?(essence|ravitaill\w*|carbu\w*|plein|fuel|refuel\w*|litres?)\b|"
           r"\bne (mets|met|mettez|ajoute|rajoute|remets) (pas|rien) (d |de )?(essence|carbu)|"
           r"\bno (fuel|refuel\w*)\b|without (fuel|refuel\w*)|don t (add )?(any )?fuel|skip (the )?(fuel|refuel\w*)")
FUEL_SET = None   # fonction() : pas d'essence au prochain arrêt ; renvoie True si le menu est re-réglé


def fuel_command(t: str) -> str | None:
    """« sans ravitaillement » / « pas d'essence » : on ne remet pas d'essence au prochain arrêt."""
    if re.search(r"^(il faut|faut il|est ce qu|on doit|je dois|tu crois|ca vaut)", t) or not re.search(NO_FUEL, t):
        return None
    if FUEL_SET is None:
        return L("Je ne peux pas changer l'essence pour l'instant.", "I can't change the fuel right now.")
    menu = FUEL_SET()
    out = L("C'est noté, pas d'essence au prochain arrêt.", "Copy, no fuel at the next stop.")
    return out + (L(" Je corrige le menu des stands.", " Updating the pit menu.") if menu else "")


# ---- pneus pneu par pneu : « change juste les deux avant », « les pneus gauches », « garde les pneus »
TYRES_SET = None   # fonction(roues: tuple d'indices 0=AVG 1=AVD 2=ARG 3=ARD) ; renvoie True si le menu est re-réglé
_FRONT, _REAR, _LEFT, _RIGHT = r"avants?|fronts?", r"arrieres?|rears?|back", r"gauches?|left", r"droite?s?|right"


def wheels_text(w) -> str:
    """(0, 1) -> « les deux pneus avant »"""
    w = tuple(sorted(w))
    named = {(): L("on garde les pneus", "we keep the tyres"), (0, 1, 2, 3): L("les quatre pneus", "all four tyres"),
             (0, 1): L("les deux pneus avant", "the two fronts"), (2, 3): L("les deux pneus arrière", "the two rears"),
             (0, 2): L("les deux pneus gauches", "the two left tyres"), (1, 3): L("les deux pneus droits", "the two right tyres")}
    if w in named:
        return named[w]
    if len(w) == 1:
        return L(f"le pneu {_tyre_names(list(w))}", f"the {_tyre_names(list(w))} tyre")
    names = [_tyre_names([i]) for i in w]
    return L("les pneus ", "the ") + ", ".join(names[:-1]) + L(" et ", " and ") + names[-1] + L("", " tyres")


def parse_wheels(t: str):
    """Renvoie un tuple de roues, () pour « on garde les pneus », ou None si la phrase ne parle pas de changer des pneus."""
    if not re.search(r"\b(pneus?|gommes?|roues?|tyres?|tires?|wheels?)\b|\bles (deux|2|quatre|4) (avant|arriere|gauche|droit)|"
                     r"\b(seulement|juste|que|change|changez|uniquement) (l |le |les )?(avant|arriere)s? (gauche|droit)", t):
        return None
    if re.search(r"^(il faut|faut il|est ce qu|on doit|je dois|tu crois|ca vaut|comment|combien|quel|quand)", t):
        return None   # une question sur les pneus, pas un ordre
    if re.search(r"\b(pluie|mouille|wets?|slicks?|secs?)\b", t):
        return None   # le type de pneus (pluie / slicks) est géré par la stratégie météo
    if re.search(r"\b(garde|gardez|garder|on garde|laisse|laisser)\b.*\b(pneus?|gommes?)\b|"
                 r"\b(pas|aucun|sans) (de |d |les |le )?(changement de )?(pneus?|gommes?)\b|"
                 r"\bne (change|changez|changer|touche|touchez) (pas|rien)\b.*\bpneu|keep (the )?tyres|no (new )?tyres", t):
        return ()
    if not re.search(r"\b(change|changez|changer|changes|remplace|remplacer|mets|met|mettez|monte|chausse|prepare|preparez|prevois|"
                     r"seulement|juste|que|uniquement|neufs?|nouveaux?|change|swap|new|only|just|fit)\b", t):
        return None
    if re.search(r"\b(quatre|4|tous|toutes|all|four)\b", t):
        return (0, 1, 2, 3)
    f, r = bool(re.search(rf"\b({_FRONT})", t)), bool(re.search(rf"\b({_REAR})", t))
    l, d = bool(re.search(rf"\b({_LEFT})\b", t)), bool(re.search(rf"\b({_RIGHT})\b", t))
    one = bool(re.search(r"\b(le|un|l|seul|one) (seul )?(pneu |tyre |tire )?(avant|arriere|front|rear)\b", t)) and \
        not re.search(r"\b(les|deux|2|two|both)\b", t)
    if not (f or r or l or d):
        # « change les pneus » sans préciser : les quatre
        return (0, 1, 2, 3) if re.search(r"\b(change|changez|changer|remplace|mets|met)\b.*\b(pneus|tyres|tires)\b", t) else None
    fr = [0, 1] if f and not r else [2, 3] if r and not f else [0, 1, 2, 3]   # indices des roues retenues (avant / arrière)
    side = [0, 2] if l and not d else [1, 3] if d and not l else [0, 1, 2, 3]
    w = tuple(i for i in range(4) if i in fr and i in side)
    if one and len(w) > 1 and not (l or d):
        return None   # « le pneu avant » sans côté : trop flou
    return w or None


def tyre_command(t: str) -> str | None:
    w = parse_wheels(t)
    if w is None:
        return None
    if TYRES_SET is None:
        return L("Je ne peux pas changer les pneus pour l'instant.", "I can't change the tyres right now.")
    menu = TYRES_SET(w)
    if not w:
        out = L("C'est noté, on garde les pneus au prochain arrêt.", "Copy, we keep the tyres at the next stop.")
    else:
        what = wheels_text(w)
        out = L(f"C'est noté, on change {what} au prochain arrêt.", f"Copy, we change {what} at the next stop.")
    return out + (L(" Je corrige le menu des stands.", " Updating the pit menu.") if menu else "")


NUM_WORDS = {"un": 1, "premier": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
             "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15}


def _wanted_place(t: str) -> int | None:
    """« P6 », « p 6 », « pe six », « le 6e », « la sixième », « position 6 » -> 6."""
    m = re.search(r"\bp ?(\d{1,2})\b|\bposition (\d{1,2})\b|\b(\d{1,2}) ?(e|eme|ieme)\b", t)
    if m:
        return int(next(g for g in m.groups()[:3] if g))
    m = re.search(r"\b(?:pe|pee|p) (" + "|".join(NUM_WORDS) + r")\b", t)
    if m:
        return NUM_WORDS[m.group(1)]
    m = re.search(r"\b(" + "|".join(w[:-1] if w.endswith("e") else w for w in NUM_WORDS if w not in ("un", "premier")) + r")ieme\b", t)
    if m:
        for w, n in NUM_WORDS.items():
            if (w[:-1] if w.endswith("e") else w) == m.group(1):
                return n
    return None


def rival(t: str, s: Snapshot) -> str | None:
    """Question sur une voiture précise : « où est P6 ? », « P2 roule plus vite ? », « dans quel secteur P6 est plus rapide ? »."""
    if not s.rivals or re.search(r"\b(je suis|suis je|ma position|ma place)\b", t):
        return None
    n = _wanted_place(t)
    if n is None:
        return None
    me_pos = s.class_position or s.position
    if n == me_pos and not any(r.get("place") == n for r in s.rivals):
        return L(f"P{n}, c'est toi !", f"P{n}, that's you!")
    # P = position générale si une voiture de ta catégorie l'occupe, sinon position dans ta catégorie
    car = next((r for r in s.rivals if r.get("place") == n), None) or next((r for r in s.rivals if r.get("cpos") == n), None)
    if car is None:
        return L(f"Je ne vois pas de P{n} dans ta catégorie.", f"I can't see a P{n} in your class.")
    name = (car.get("name") or "").split(" ")[-1] or L("ce pilote", "that driver")
    who = f"P{n}, {name},"
    parts = []
    g = car.get("gap")
    if car.get("in_pits"):
        parts.append(L(f"{who} est aux stands.", f"{who} is in the pits."))
    elif g is not None:
        parts.append(L(f"{who} est {_sec(abs(g))} {'devant' if g > 0 else 'derrière'} toi.",
                       f"{who} is {_sec(abs(g))} {'ahead of' if g > 0 else 'behind'} you."))
    else:
        parts.append(L(f"{who} n'est pas dans le même tour que toi.", f"{who} isn't on the same lap as you."))
    mine, his = s.last_lap, car.get("last_lap")
    if mine and his:
        d = his - mine
        if abs(d) < 0.1:
            parts.append(L("Vous tournez dans le même rythme.", "You're lapping at the same pace."))
        else:
            parts.append(L(f"Il tourne {_f(abs(d))} seconde{'s' if abs(d) >= 2 else ''} {'plus vite' if d < 0 else 'moins vite'} que toi au dernier tour.",
                           f"He was {_f(abs(d))} s {'quicker' if d < 0 else 'slower'} than you last lap."))
    if re.search(r"secteur|perd|plus rapide|plus vite|gagne|sector", t):
        a, b = s.sectors, car.get("sectors")
        if a and b and all(a) and all(b):
            diffs = [b[i] - a[i] for i in range(3)]
            i = min(range(3), key=lambda k: diffs[k])
            if diffs[i] < -0.05:
                parts.append(L(f"Il te prend le plus de temps dans le secteur {i + 1}, {_f(-diffs[i])} seconde.",
                               f"He's quickest against you in sector {i + 1}, {_f(-diffs[i])} s."))
            else:
                parts.append(L("Tu es plus rapide que lui dans les trois secteurs.", "You're quicker than him in all three sectors."))
    return " ".join(parts)


def answer(text: str, s: Snapshot, p: Plan) -> str:
    global LAST_TEXT
    c = command(text)
    if c:
        return c
    t = _norm(text).strip()
    if not t:
        return L("Je n'ai rien entendu, répète.", "I didn't hear anything, say again.")
    LAST_TEXT = t
    # ordres pour le prochain arrêt : réparations et/ou essence (« répare mais sans ravitaillement »)
    f = fuel_command(t)
    r = repair_command(t)
    w = tyre_command(t)
    orders = [x for x in (r, w, f) if x]
    if orders:
        # « répare, change les avants et pas d'essence » : une seule phrase, « je corrige le menu » une fois à la fin
        tail = [L(" Je corrige le menu des stands.", " Updating the pit menu.")]
        fix = any(tail[0] in o for o in orders)
        body = [o.replace(tail[0], "") for o in orders]
        body = [body[0]] + [b.replace("C'est noté, ", "Et ").replace("Copy, ", "And ") for b in body[1:]]
        nxt = (L(" au prochain arrêt", " at the next stop"))
        body = [b.replace(nxt, "") for b in body[:-1]] + body[-1:]
        return " ".join(body) + (tail[0] if fix else "")
    if not s.on_track:
        # hors piste, « comment ça va » est une politesse, pas une demande de point complet
        polite = bool(re.search(r"\bca va\b|comment vas tu|how are you", t))
        asks_data = any(re.search(pattern, t) for pattern, fn in TOPICS if not (polite and fn is status))
        said = chat(t, s, alone=not asks_data)
        if asks_data:
            said.append(L("Je n'ai pas encore de données, monte dans la voiture.", "No data yet, get in the car."))
        if said:
            return " ".join(said)
        return L("Je t'entends, mais je n'ai pas compris. Une fois en piste, demande-moi l'essence, les pneus, "
                 "le stand, les écarts, la position ou la météo.",
                 "I hear you, but I didn't get that. Once you're on track, ask me about fuel, tyres, "
                 "pit stop, gaps, position or weather.")
    rv = rival(t, s)
    if rv:
        return rv
    said = chat(t, s, alone=not any(re.search(pattern, t) for pattern, _ in TOPICS))
    replies = []
    for pattern, fn in TOPICS:
        if re.search(pattern, t) and fn not in [r[0] for r in replies]:
            if fn is gaps and any(r[0] in (sectors, sectors_ahead, sectors_behind) for r in replies):
                continue
            if fn is sectors and any(r[0] in (sectors_ahead, sectors_behind) for r in replies):
                continue
            if fn is laptimes and any(r[0] is record for r in replies):
                continue
            if fn is gaps and any(r[0] in (who_ahead, who_behind, leader) for r in replies):
                continue
            if fn is pit and any(r[0] is stops_count for r in replies):
                continue
            if fn is laptimes and any(r[0] in (pace_rank, lap_valid) for r in replies):
                continue
            if fn is position and any(r[0] in (leader, field_size) for r in replies):
                continue
            if fn is laps and any(r[0] is flags for r in replies):
                continue
            if fn is behavior and any(r[0] is brakes for r in replies):
                continue
            replies.append((fn, fn(s, p)))
    if not replies and not said:
        # longue phrase sans question claire (tu parlais peut-être à quelqu'un d'autre) : on demande de répéter
        if len(t.split()) > 9:
            return L("Je n'ai pas compris ta question. Pose-la-moi en une phrase courte.",
                     "I didn't get your question. Ask me in one short sentence.")
        # phrase courte : on donne le point complet
        return L("Pas sûr d'avoir compris, voilà le point. ", "Not sure I got that, here's the update. ") + status(s, p)
    return " ".join(said + [r[1] for r in replies[:3]])
