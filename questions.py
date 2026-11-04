"""
Réponses de l'ingénieur aux questions du pilote (étape 3).

On repère des mots-clés dans la phrase reconnue et on répond avec les vraies
données de course. Plusieurs sujets dans la même phrase = plusieurs réponses.
"""

from __future__ import annotations

import re
import unicodedata

from strategy import Plan
from telemetry import Snapshot
from i18n import L, dec


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
    out = L(f"Il te reste {_f(s.fuel, 0)} litres.", f"You have {_f(s.fuel, 0)} litres left.")
    if p.fuel_per_lap:
        out += L(f" Tu consommes {_f(p.fuel_per_lap)} par tour, ça fait {_f(s.fuel / p.fuel_per_lap)} tours d'essence.",
                 f" You're using {_f(p.fuel_per_lap)} a lap, that's {_f(s.fuel / p.fuel_per_lap)} laps of fuel.")
    else:
        out += L(" J'ai besoin d'encore un ou deux tours propres pour calculer la conso.",
                 " I need one or two more clean laps to work out consumption.")
    if p.stops_needed == 0:
        out += L(" C'est bon pour aller au bout.", " That's enough to the finish.")
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
        parts.append(L(f"Il reste {max(0, s.max_laps - s.laps_done)} tours.", f"{max(0, s.max_laps - s.laps_done)} laps to go."))
    elif s.time_left is not None:
        m = int(s.time_left // 60)
        parts.append(L(f"Il reste {m} minutes", f"{m} minutes to go")
                     + (L(f", environ {_f(p.laps_to_finish, 0)} tours.", f", about {_f(p.laps_to_finish, 0)} laps.") if p.laps_to_finish else "."))
    if not parts:
        return L(f"Tu as bouclé {s.laps_done} tours.", f"You've done {s.laps_done} laps.")
    return " ".join(parts)


def pit(s: Snapshot, p: Plan) -> str:
    if s.session != "course":
        return L("On n'est pas en course, pas de stratégie d'arrêt pour l'instant.", "We're not racing, no pit strategy for now.")
    if not p.ready:
        return L("Je calcule encore, donne-moi un ou deux tours propres.", "Still calculating, give me one or two clean laps.")
    if p.stops_needed == 0:
        return L("Pas besoin de rentrer, tu as de quoi finir.", "No need to pit, you can make the finish.")
    if p.laps_until_box is not None and p.laps_until_box <= 1:
        when = L("Box ce tour.", "Box this lap.")
    else:
        when = L(f"Tu rentres à la fin du tour {p.box_lap}, dans {p.laps_until_box} tours.",
                 f"You pit at the end of lap {p.box_lap}, in {p.laps_until_box} laps.")
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


def tyres(s: Snapshot, p: Plan) -> str:
    wear = [w * 100 for w in s.tyre_wear]
    worst = min(range(4), key=lambda i: wear[i])
    out = L(f"Pneus à {_f(sum(wear) / 4, 0)} % en moyenne, le plus usé c'est l'{_tyre_names([worst])} à {_f(wear[worst], 0)} %.",
            f"Tyres at {_f(sum(wear) / 4, 0)} % on average, the most worn is the {_tyre_names([worst])} at {_f(wear[worst], 0)} %.")
    if p.tyre_laps_left is not None:
        out += L(f" Encore environ {_f(p.tyre_laps_left, 0)} tours avant qu'ils soient vraiment usés.",
                 f" About {_f(p.tyre_laps_left, 0)} more laps before they're really worn.")
    temps = s.tyre_temp
    if any(temps):
        out += L(f" Températures autour de {_f(sum(temps) / 4, 0)} degrés.", f" Temperatures around {_f(sum(temps) / 4, 0)} degrees.")
    return out


def gaps(s: Snapshot, p: Plan) -> str:
    parts = []
    if s.gap_ahead is not None:
        parts.append(L(f"{_f(s.gap_ahead)} seconde devant", f"{_f(s.gap_ahead)} seconds ahead"))
    if s.gap_behind is not None:
        parts.append(L(f"{_f(s.gap_behind)} derrière", f"{_f(s.gap_behind)} behind"))
    if not parts:
        return L("Personne de proche autour de toi.", "Nobody close around you.")
    return L("Écart : ", "Gaps: ") + ", ".join(parts) + "."


def position(s: Snapshot, p: Plan) -> str:
    out = L(f"Tu es P{s.position}", f"You're P{s.position}")
    if s.class_position and s.class_position != s.position:
        out += L(f", P{s.class_position} dans ta catégorie", f", P{s.class_position} in class")
    return out + "."


def weather(s: Snapshot, p: Plan) -> str:
    out = L(f"{p.weather or 'Sec'}. Air {_f(s.air_temp, 0)} degrés, piste {_f(s.track_temp, 0)}.",
            f"{p.weather or 'Dry'}. Air {_f(s.air_temp, 0)} degrees, track {_f(s.track_temp, 0)}.")
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
    (r"pneu|gomme|usure|\btyre|\btire|rubber|\bwear", tyres),
    (r"ecart|devant|derriere|\bgap|attaque|revient|ahead|behind|in front|catching", gaps),
    (r"position|place|classement|quelle p\b|combien.*(je suis|suis je)|where am i|what p\b", position),
    (r"meteo|pluie|pleut|pleuvoir|mouill|humid|sec\b|temperature|nuage|weather|\brain|\bwet\b|\bdry\b|cloud", weather),
    (r"chrono|dernier tour|meilleur tour|temps au tour|mon tour|rythme|lap time|last lap|best lap|\bpace\b", laptimes),
    (r"combien de tour|tours restant|reste.*tour|temps restant|reste.*minute|\bfin\b|arrivee|damier|how many laps|laps (left|to go|remaining)|time (left|remaining)|finish", laps),
    (r"point complet|situation|resume|tout va|comment ca va|ca donne quoi|recap|update|summary|how are we|status|how s it going", status),
]


LAPTIMES = None  # branché par app.py
BEHAVIOR = None
PIT_ACTION = None   # fonction appelée pour régler le menu des stands


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
    (r"(prepare|regle|mets|programme|set up|setup the|program).*(stand|arret|box|menu|pit|stop)|(stand|arret).*(prepare|regle)", pit_command),
    (r"comporte|sous vir|sousvir|survir|equilibr|reglage|setup|conseil|glisse|bloqu|patin|tient pas|braqu|tourne pas|ralenti|pousse|lourde|decroche|chasse|instable|nerveuse|freinage|balance|understeer|oversteer|handling|advice|sliding|locking|wheelspin|loose|snap|braking|won t turn", behavior),
    (r"record|meilleur temps (ici|du circuit)|tour ideal|personal best|ideal lap", record),
    (r"(secteur|perd|gagne|reprend|compar|plus rapide|plus lent|sector|losing|gaining|faster|slower).*(devant|ahead|in front)|(devant|ahead|in front).*(secteur|perd|gagne|rapide|lent|sector|losing|gaining|faster|slower)", sectors_ahead),
    (r"(secteur|perd|gagne|reprend|compar|plus rapide|plus lent|sector|losing|gaining|faster|slower).*(derriere|behind)|(derriere|behind).*(secteur|perd|gagne|rapide|lent|sector|losing|gaining|faster|slower)", sectors_behind),
    (r"secteur|ou je perds|ou je gagne|ou est ce que je perds|compar|sector|where am i losing|where do i lose", sectors),
]


VOICE = None      # pour le mode silence
ENG = None        # pour répéter le dernier message

COMMANDS = [
    (r"\bsilence\b|tais toi|taise|chut\b|moins de message|arrete de parler|mode calme|plus que l urgent|be quiet|shut up|quiet mode|less talk|only urgent", "quiet"),
    (r"reparle|parle a nouveau|tu peux parler|fin du silence|toutes les infos|remets? (la radio|les annonces)|talk again|you can talk|all info|unmute|resume radio", "talk"),
    (r"repete|redis|redire|j ai pas (compris|entendu)|pardon\b|t as dit quoi|qu est ce que tu as dit|repeat|say again|come again|what did you say", "repeat"),
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
    return L("Oui, je t'entends, cinq sur cinq.", "Yes, I hear you loud and clear.")


def _here(s: Snapshot) -> str:
    return L("Je suis là, je t'écoute.", "I'm here, go ahead.")


def _hello(s: Snapshot) -> str:
    return L("Salut ! Je suis là, prête quand tu veux.", "Hi! I'm here, ready when you are.")


def _thanks(s: Snapshot) -> str:
    return L("Avec plaisir.", "You're welcome.")


def _who(s: Snapshot) -> str:
    return L("Je suis Jessica, ton ingénieure de course.", "I'm Jessica, your race engineer.")


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
    return L("Ça va très bien, merci ! Prête pour la course.", "All good, thanks! Ready for the race.")


def _joke(s: Snapshot) -> str:
    return L("Les blagues, c'est après le drapeau à damier. Reste concentré !",
             "Jokes are for after the chequered flag. Stay focused!")


CHAT = [
    (r"\bm entends?\b|\bm entendez\b|tu me recois|me recois tu|tu recois|radio check|test radio|\ballo\b|"
     r"can you hear|do you hear|hear me|do you copy|you copy", _radio_check),
    (r"\b(t es|tu es|es tu|t es bien) la\b|t es toujours la|you there|are you there", _here),
    (r"^(bonjour|salut|hello|coucou|hey|bonsoir|hi)\b", _hello),
    (r"\bmerci\b|thank", _thanks),
    (r"qui es tu|t es qui|tu es qui|comment tu t appelles|ton nom|ton prenom|who are you|your name", _who),
    (r"que (peux|sais) tu|qu est ce que tu (peux|sais)|tu sais faire|tu peux faire quoi|\baide\b|\bhelp\b|what can you", _help),
    (r"quelle heure|l heure qu il|what time", _time),
    (r"\bca va\b|comment vas tu|how are you", _how_are_you),
    (r"blague|joke|funny", _joke),
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


def answer(text: str, s: Snapshot, p: Plan) -> str:
    c = command(text)
    if c:
        return c
    t = _norm(text).strip()
    if not t:
        return L("Je n'ai rien entendu, répète.", "I didn't hear anything, say again.")
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
            replies.append((fn, fn(s, p)))
    if not replies and not said:
        # jamais sans réponse : on donne le point complet
        return L("Pas sûr d'avoir compris, voilà le point. ", "Not sure I got that, here's the update. ") + status(s, p)
    return " ".join(said + [r[1] for r in replies[:3]])
