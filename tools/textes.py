"""Textes à traduire d'Apex Radio.

Le français et l'anglais sont écrits dans le code (L("français", "English") et les paires de
phrases variées). Cet outil les retrouve tous et tient à jour un fichier par langue :

    python tools/textes.py de --nom Deutsch --virgule     crée ou met à jour traductions/de.json
    python tools/textes.py de                             met à jour (garde les traductions déjà faites)
    python tools/textes.py --stats                        avancement de chaque langue

Dans traductions/<code>.json, le traducteur remplit seulement « texte » (il peut s'aider de « en »).
Les {0}, {1}… sont des valeurs remplies par l'appli (nombres, noms) : à garder, dans l'ordre voulu.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "traductions"
SKIP = {"build_public.py", "lmu_probe.py"}


def _is_text(n) -> bool:
    return isinstance(n, ast.JoinedStr) or (isinstance(n, ast.Constant) and isinstance(n.value, str))


def _template(n, slots: dict) -> str:
    """Texte avec {0}, {1}… à la place des valeurs. `slots` numérote chaque expression (même numéro en fr et en en)."""
    if isinstance(n, ast.Constant):
        return n.value
    out = []
    for v in n.values:
        if isinstance(v, ast.Constant):
            out.append(str(v.value))
        else:
            key = ast.unparse(v.value) + ("!" + chr(v.conversion) if v.conversion > 0 else "") + \
                (":" + ast.unparse(v.format_spec) if v.format_spec else "")
            if key not in slots:
                slots[key] = len(slots)
            out.append("{%d}" % slots[key])
    return "".join(out)


def _align(fr: str, en: str) -> str:
    """Si l'anglais calcule une valeur autrement (ex. le « s » du pluriel), on lui donne le numéro de la valeur
    française à la même place, pour que le traducteur n'ait que des numéros qui existent."""
    import re
    f_ids = re.findall(r"\{(\d+)\}", fr)
    e_ids = re.findall(r"\{(\d+)\}", en)
    if not set(e_ids) - set(f_ids) or len(e_ids) != len(f_ids):
        return en
    it = iter(f_ids)
    return re.sub(r"\{(\d+)\}", lambda m: "{%s}" % next(it), en)


def extract() -> list[dict]:
    found: dict[str, dict] = {}
    for f in sorted(ROOT.glob("*.py")):
        if f.name in SKIP:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), str(f))
        inside_L = set()
        pairs = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "L" \
                    and len(node.args) >= 2 and _is_text(node.args[0]) and _is_text(node.args[1]):
                pairs.append((node.args[0], node.args[1], node.lineno))
                inside_L.add(id(node.args[0]))
        for node in ast.walk(tree):   # mots au pluriel : plural(n, "tour", "lap") -> « tour » et « tours »
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "plural" \
                    and len(node.args) >= 3 and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args[1:3]):
                fw, ew = node.args[1].value, node.args[2].value
                pairs.append((ast.Constant(fw), ast.Constant(ew), node.lineno))
                pairs.append((ast.Constant(fw + "s"), ast.Constant(ew + "s"), node.lineno))
                inside_L.update((id(node.args[1]), id(node.args[2])))
        for node in ast.walk(tree):   # paires (français, anglais) des phrases variées : pick(…, [("…", "…"), …])
            if isinstance(node, ast.Tuple) and len(node.elts) == 2 and all(_is_text(e) for e in node.elts) \
                    and id(node.elts[0]) not in inside_L:
                pairs.append((node.elts[0], node.elts[1], node.lineno))
        for a, b, line in pairs:
            slots: dict = {}
            fr, en = _template(a, slots), _template(b, slots)
            en = _align(fr, en)
            if not any(c.isalpha() for c in fr) or fr == en and len(fr) < 4:
                continue
            found.setdefault(fr, {"fr": fr, "en": en, "ou": f"{f.name}:{line}"})
    for fr, en, where in extract_ui():
        if any(c.isalpha() for c in fr) and not (fr == en and len(fr) < 4):
            found.setdefault(fr, {"fr": fr, "en": en, "ou": where})
    return sorted(found.values(), key=lambda e: (e["ou"].startswith("ui/"), e["ou"]))


# ------------------------------------------------------------------ tableau de bord (ui/*.html)
def _norm(s: str) -> str:
    import html
    import re
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _js_string(src: str, i: int):
    """Lit une chaîne JS ("…", '…' ou `…${x}…`) qui commence en src[i]. Renvoie (modèle, slots, fin) ou None."""
    q = src[i] if i < len(src) else ""
    if q not in "\"'`":
        return None
    out, exprs, j = [], [], i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            out.append(src[j + 1] if j + 1 < len(src) else "")
            j += 2
            continue
        if c == q:
            return "".join(out), exprs, j + 1
        if q == "`" and src.startswith("${", j):
            depth, k = 1, j + 2
            while k < len(src) and depth:
                depth += {"{": 1, "}": -1}.get(src[k], 0)
                k += 1
            exprs.append(src[j + 2:k - 1].strip())
            out.append("\0%d\0" % (len(exprs) - 1))
            j = k
            continue
        out.append(c)
        j += 1
    return None


def _slot(text: str, exprs: list, slots: dict) -> str:
    import re

    def rep(m):
        e = exprs[int(m.group(1))]
        if e not in slots:
            slots[e] = len(slots)
        return "{%d}" % slots[e]
    return re.sub(r"\0(\d+)\0", rep, text)


def extract_ui() -> list[tuple[str, str, str]]:
    import re
    out = []
    for f in sorted((ROOT / "ui").glob("*.html")):
        src = f.read_text(encoding="utf-8")
        line = lambda pos: src.count("\n", 0, pos) + 1
        # T("français", "English") et T(`… ${x} …`, `…`)
        for m in re.finditer(r"\bT\(\s*", src):
            a = _js_string(src, m.end())
            if not a:
                continue
            k = a[2]
            while k < len(src) and src[k] in " \n\t,":
                k += 1
            b = _js_string(src, k)
            if not b:
                continue
            slots: dict = {}
            fr, en = _slot(a[0], a[1], slots), _slot(b[0], b[1], slots)
            out.append((_norm(fr), _norm(_align(fr, en)), f"ui/{f.name}:{line(m.start())}"))
        # listes d'options ["clé", "français", "English"]
        for m in re.finditer(r'\[\s*"[^"\n]*"\s*,\s*"([^"\n]+)"\s*,\s*"([^"\n]+)"\s*\]', src):
            out.append((_norm(m.group(1)), _norm(m.group(2)), f"ui/{f.name}:{line(m.start())}"))
        # <balise data-en="English">français</balise>
        for m in re.finditer(r'<(\w+)\b[^>]*?\sdata-en="([^"]*)"[^>]*>(.*?)</\1>', src, re.S):
            out.append((_norm(m.group(3)), _norm(m.group(2)), f"ui/{f.name}:{line(m.start())}"))
        # attributs : title / placeholder / aria-label avec leur version data-en-…
        for tag in re.finditer(r"<[^>]+>", src):
            s = tag.group(0)
            for attr, en_attr in (("title", "data-en-title"), ("placeholder", "data-en-placeholder"), ("aria-label", "data-en-aria")):
                a = re.search(r'\s%s="([^"]*)"' % attr, s)
                b = re.search(r'\s%s="([^"]*)"' % en_attr, s)
                if a and b:
                    out.append((_norm(a.group(1)), _norm(b.group(1)), f"ui/{f.name}:{line(tag.start())}"))
    return out


def update(code: str, name: str | None, comma: bool | None) -> None:
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{code}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    done = {e["fr"]: e.get("texte", "") for e in old.get("textes", []) if e.get("texte")}
    texts = extract()
    for e in texts:
        e["texte"] = done.pop(e["fr"], "")
    data = {
        "_langue": name or old.get("_langue", code),
        "_virgule_decimale": comma if comma is not None else old.get("_virgule_decimale", False),
        "_aide": "Remplis « texte » pour chaque phrase (aide : « en »). Garde les {0}, {1}… : ce sont des valeurs.",
        "textes": texts,
    }
    if done:   # traductions de phrases qui n'existent plus dans l'appli : gardées à part
        data["_anciennes"] = done
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(1 for e in texts if e["texte"])
    print(f"{path.relative_to(ROOT)} : {len(texts)} textes, {n} traduits ({100 * n // max(1, len(texts))} %)")


def stats() -> None:
    texts = extract()
    print(f"{len(texts)} textes dans l'appli")
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        have = {e["fr"] for e in d.get("textes", []) if e.get("texte")}
        n = sum(1 for e in texts if e["fr"] in have)
        print(f"  {f.stem} ({d.get('_langue', '?')}) : {n}/{len(texts)} ({100 * n // max(1, len(texts))} %)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("code", nargs="?", help="code de la langue (de, es, it, tr…)")
    ap.add_argument("--nom", help="nom de la langue dans sa langue (Deutsch, Español…)")
    ap.add_argument("--virgule", action="store_true", default=None, help="la langue écrit 3,6 et pas 3.6")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.stats or not a.code:
        stats()
    elif a.code in ("fr", "en"):
        sys.exit("Le français et l'anglais sont directement dans le code.")
    else:
        update(a.code.lower(), a.nom, a.virgule)
