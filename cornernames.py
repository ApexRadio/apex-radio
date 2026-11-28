"""
Noms des virages célèbres.

Apex numérote les virages qu'il repère sur la carte (1, 2, 3…). Sur les circuits où certains virages ont un nom
connu (le Raidillon, Mulsanne, la Parabolica…), on remplace « virage 3 » par ce nom dans tout ce que dit l'ingénieur.

Chaque nom est rangé par sa position dans le tour (0 = ligne d'arrivée, 1 = tour complet), mesurée sur les cartes
enregistrées dans LMU. Un virage repéré à moins de TOL de cette position prend le nom.
Le nom français porte son article (« le Raidillon », « les Esses ») pour bien dire « au Raidillon », « des Esses ».
"""

from __future__ import annotations

import re
import unicodedata

TOL = 0.012

# (motif dans le nom du circuit, [(position, nom français avec article, nom anglais), ...])
TABLE = [
    (r"sarthe|le mans", [
        (0.105, "les Esses", "the Esses"),
        (0.14, "le Tertre Rouge", "Tertre Rouge"),
        (0.568, "Mulsanne", "Mulsanne"),
        (0.72, "Indianapolis", "Indianapolis"),
        (0.745, "Arnage", "Arnage"),
        (0.845, "les virages Porsche", "the Porsche Curves"),
        (0.895, "les virages Porsche", "the Porsche Curves"),
        (0.97, "la chicane Ford", "the Ford chicane"),
        (0.995, "la chicane Ford", "the Ford chicane"),
    ]),
    (r"\bspa\b|francorchamps", [
        (0.037, "la Source", "La Source"),
        (0.11, "l'Eau Rouge", "Eau Rouge"),
        (0.145, "le Raidillon", "Raidillon"),
        (0.325, "les Combes", "Les Combes"),
        (0.343, "les Combes", "Les Combes"),
        (0.362, "Malmedy", "Malmedy"),
        (0.417, "Rivage", "Rivage"),
        (0.545, "Pouhon", "Pouhon"),
        (0.625, "Fagnes", "Fagnes"),
        (0.65, "Fagnes", "Fagnes"),
        (0.69, "Stavelot", "Stavelot"),
        (0.723, "Paul Frère", "Paul Frère"),
        (0.953, "le Bus Stop", "the Bus Stop"),
    ]),
    (r"monza", [
        (0.013, "la première chicane", "the first chicane"),
        (0.025, "la première chicane", "the first chicane"),
        (0.052, "la première chicane", "the first chicane"),
        (0.165, "la Curva Grande", "Curva Grande"),
        (0.362, "la Roggia", "Roggia"),
        (0.378, "la Roggia", "Roggia"),
        (0.438, "Lesmo 1", "Lesmo 1"),
        (0.494, "Lesmo 2", "Lesmo 2"),
        (0.677, "Ascari", "Ascari"),
        (0.698, "Ascari", "Ascari"),
        (0.714, "Ascari", "Ascari"),
        (0.905, "la Parabolica", "Parabolica"),
    ]),
    (r"paul ricard|castellet", [
        (0.043, "le S de la Verrerie", "the Verrerie S"),
        (0.268, "le virage du Camp", "Le Camp"),
        (0.515, "la chicane du Mistral", "the Mistral chicane"),
        (0.667, "Signes", "Signes"),
        (0.757, "le double droite du Beausset", "the Beausset double right"),
        (0.823, "Bendor", "Bendor"),
    ]),
    (r"daytona", [
        (0.168, "l'International Horseshoe", "the International Horseshoe"),
        (0.307, "le West Horseshoe", "the West Horseshoe"),
        (0.662, "le Bus Stop", "the Bus Stop"),
        (0.685, "le Bus Stop", "the Bus Stop"),
    ]),
    (r"road atlanta", [
        (0.2, "les Esses", "the Esses"),
        (0.233, "les Esses", "the Esses"),
        (0.275, "les Esses", "the Esses"),
        (0.855, "la chicane", "the chicane"),
        (0.882, "la chicane", "the chicane"),
    ]),
    (r"interlagos|jose carlos pace", [
        (0.098, "le S de Senna", "the Senna S"),
        (0.155, "la Curva do Sol", "Curva do Sol"),
        (0.215, "la Descida do Lago", "Descida do Lago"),
        (0.237, "la Descida do Lago", "Descida do Lago"),
        (0.355, "la Ferradura", "Ferradura"),
        (0.492, "Laranjinha", "Laranjinha"),
        (0.64, "le Bico de Pato", "Bico de Pato"),
        (0.77, "le Mergulho", "Mergulho"),
        (0.858, "la Junção", "Junção"),
    ]),
    (r"brands hatch(?!.*indy)", [
        (0.07, "Paddock Hill", "Paddock Hill Bend"),
        (0.155, "Druids", "Druids"),
        (0.215, "Graham Hill", "Graham Hill Bend"),
        (0.318, "Surtees", "Surtees"),
        (0.522, "Hawthorn", "Hawthorn"),
        (0.605, "Westfield", "Westfield"),
        (0.703, "Dingle Dell", "Dingle Dell"),
        (0.767, "Stirling's", "Stirling's"),
        (0.895, "Clearways", "Clearways"),
        (0.968, "Clark Curve", "Clark Curve"),
    ]),
    (r"barcelona|catalunya", [
        (0.043, "Elf", "Elf"),
        (0.065, "Elf", "Elf"),
        (0.177, "Renault", "Renault"),
        (0.205, "Repsol", "Repsol"),
        (0.255, "Seat", "Seat"),
    ]),
]

ACTIVE: dict[int, tuple[str, str]] = {}     # virages nommés du circuit en cours : id → (fr, en)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def names_for(track: str, corners: list[dict]) -> dict[int, tuple[str, str]]:
    """Associe aux virages repérés (id, mid) le nom connu le plus proche."""
    t = _norm(track)
    rows = next((r for pat, r in TABLE if re.search(pat, t)), None)
    out = {}
    if not rows:
        return out
    for c in corners:
        best = min(rows, key=lambda r: min(abs(r[0] - c["mid"]), 1 - abs(r[0] - c["mid"])))
        d = min(abs(best[0] - c["mid"]), 1 - abs(best[0] - c["mid"]))
        if d <= TOL:
            out[c["id"]] = (best[1], best[2])
    return out


def _a(fr: str) -> str:
    """« au Raidillon », « aux Esses », « à la Source », « à l'Eau Rouge », « à Mulsanne »."""
    if fr.startswith("le "):
        return "au " + fr[3:]
    if fr.startswith("les "):
        return "aux " + fr[4:]
    return "à " + fr


def _de(fr: str) -> str:
    """« du Raidillon », « des Esses », « de la Source », « de l'Eau Rouge », « d'Arnage », « de Mulsanne »."""
    if fr.startswith("le "):
        return "du " + fr[3:]
    if fr.startswith("les "):
        return "des " + fr[4:]
    if fr.startswith(("la ", "l'")):
        return "de " + fr
    return ("d'" if _norm(fr[:1]) in "aeiouy" else "de ") + fr


def rename(text: str) -> str:
    """Remplace « virage 3 » / « turn 3 » par le nom du virage quand il en a un."""
    if not ACTIVE or not text:
        return text

    def fr(m):
        prep, n = (m.group(1) or "").lower(), int(m.group(2))
        if n not in ACTIVE:
            return m.group(0)
        name = ACTIVE[n][0]
        cap = m.group(0)[:1].isupper()
        if prep == "au ":
            out = _a(name)
        elif prep == "du ":
            out = _de(name)
        elif prep == "le ":
            out = name
        else:
            out = _a(name)          # « virage 3, tu freines… » → « au Raidillon, tu freines… »
        return out[:1].upper() + out[1:] if cap else out

    text = re.sub(r"\b(au |du |le )?virage (\d+)\b", fr, text, flags=re.I)

    def en(m):
        n = int(m.group(1))
        return ACTIVE[n][1] if n in ACTIVE else m.group(0)

    return re.sub(r"\b[Tt]urn (\d+)\b", en, text)
