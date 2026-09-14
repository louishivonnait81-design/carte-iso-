"""Prepare une UNITE a coller dans le modele, et reprend le dessin qui revient.

    python unit_manual.py export u83180702
    python unit_manual.py import u83180702 dessin.png
    python unit_manual.py status

Deux differences avec le mode tuile, et elles decoulent l'une de l'autre.

Le prompt est court : il n'a plus a parler de position, de cadrage de tuile ni de
ce qui existe ailleurs sur la carte. Le compositeur place le dessin, donc le
modele n'a plus que deux contraintes — garder la silhouette et garder le cadre —
et une liste de ce qu'il faut poser dessus.

Et l'image partie au modele est CARREE. Les modeles d'image recopient le rapport
de forme de leur entree : une unite de 1423x1673 revenait avec quelques pour cent
d'ecart, et remettre ce dessin a l'echelle de sa boite l'aurait deforme. L'unite
est donc centree sur un carre blanc, et l'import redecoupe exactement la fenetre
d'origine. Le decalage est enregistre dans meta.json, pas recalcule.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
UNITS = ROOT / "units"
DRAWN = ROOT / "drawn"
OUT = ROOT / "manual_units"
REF01 = ROOT / "assets" / "REF_01_style.png"
TEMPLATE = ROOT / "prompts" / "unit.md"
LIEUX = ROOT / "prompts" / "lieux.md"


def load_index() -> dict:
    path = UNITS / "index.json"
    if not path.exists():
        raise SystemExit(f"{path} introuvable : lancer `make units` d'abord.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_fiches() -> dict[str, str]:
    """Fiches de lieux, indexees par le motif cherche dans le nom OSM."""
    if not LIEUX.exists():
        return {}
    fiches = {}
    for line in LIEUX.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- \*\*(.+?)\*\*\s*:\s*(.+)", line)
        if m:
            fiches[m.group(1).lower()] = m.group(2).strip()
    return fiches


def note_for(entry: dict, fiches: dict[str, str], names: dict[int, str]) -> str:
    """Fiche a joindre si l'unite porte un batiment nomme que l'on connait."""
    seen = []
    for wid in entry["way_ids"]:
        name = (names.get(wid) or "").lower()
        if not name:
            continue
        for pattern, text in fiches.items():
            if pattern in name and text not in seen:
                seen.append(text)
    if not seen:
        return ""
    body = "\n".join(f"  {t}" for t in seen)
    return ("\n\nWHAT THIS ROW REALLY IS. Draw it as described here; this description "
            "was written from a photograph and wins over the general rules above.\n"
            + body + "\n")


def squared(image: Image.Image) -> tuple[Image.Image, tuple[int, int, int]]:
    """Centre l'image sur un carre blanc. Renvoie (carre, (offset_x, offset_y, cote))."""
    side = max(image.size)
    canvas = Image.new("L", (side, side), 255)
    ox, oy = (side - image.width) // 2, (side - image.height) // 2
    canvas.paste(image, (ox, oy))
    return canvas, (ox, oy, side)


def build_prompt(entry: dict, note: str) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text[text.index("-->") + 3:].lstrip("\n")
    return text.format(ref01=1, lines=2, note=note).rstrip() + "\n"


def export(name: str, index: dict, extra_note: str, force: bool) -> Path:
    entry = next((e for e in index["units"] if e["name"] == name), None)
    if entry is None:
        raise SystemExit(f"Unite inconnue : {name}")
    if not REF01.exists():
        raise SystemExit(f"{REF01} introuvable.")

    folder = OUT / name
    if folder.exists():
        if not force:
            raise SystemExit(f"{folder} existe deja : --force pour la refaire.")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    lines = Image.open(UNITS / entry["line"]).convert("L")
    square, (ox, oy, side) = squared(lines)
    shutil.copy(REF01, folder / "1_ref01.png")
    square.save(folder / "2_lines.png")

    names = {int(k): v for k, v in index.get("names", {}).items()}
    fiche = note_for(entry, load_fiches(), names)
    note = fiche + (f"\n\n{extra_note.strip()}\n" if extra_note else "")
    (folder / "prompt.txt").write_text(build_prompt(entry, note), encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps(
        {"unit": name, "pad": [ox, oy], "square": side,
         "size": [entry["w"], entry["h"]], "box": [entry["x"], entry["y"]]},
        indent=2), encoding="utf-8")

    print(f"[unite] {folder}")
    print(f"     image 1 : 1_ref01.png   REF_01 — style de trait")
    print(f"     image 2 : 2_lines.png   l'unite, centree sur un carre de {side} px")
    print(f"     la fenetre utile est {entry['w']}x{entry['h']} px a ({ox}, {oy})")
    if fiche:
        print("     une fiche de lieu est jointe au prompt")
    if extra_note:
        print("     une consigne libre est jointe au prompt")
    return folder


def import_drawing(name: str, source: Path, allow_nonsquare: bool) -> Path:
    meta_path = OUT / name / "meta.json"
    if not meta_path.exists():
        raise SystemExit(f"{meta_path} introuvable : exporter l'unite d'abord.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    art = Image.open(source).convert("L")
    if art.width != art.height and not allow_nonsquare:
        raise SystemExit(
            f"{source} n'est pas carree ({art.width}x{art.height}). Le modele a "
            f"recadre : refaire, ou forcer avec --allow-nonsquare.")

    side = meta["square"]
    if art.size != (side, side):
        art = art.resize((side, side), Image.LANCZOS)
    ox, oy = meta["pad"]
    w, h = meta["size"]
    cropped = art.crop((ox, oy, ox + w, oy + h))

    DRAWN.mkdir(exist_ok=True)
    out = DRAWN / f"{name}.png"
    cropped.save(out)
    print(f"[unite] {source.name} -> {out}  {cropped.width}x{cropped.height}")
    return out


def status(index: dict) -> None:
    done = sorted(p.stem for p in DRAWN.glob("*.png")) if DRAWN.exists() else []
    total = len(index["units"])
    print(f"[unites] {len(done)}/{total} dessinees")
    for entry in sorted(index["units"], key=lambda e: e["order"]):
        mark = "##" if entry["name"] in done else ".."
        print(f"   {mark} {entry['name']:<12} {entry['w']:>5}x{entry['h']:<5} "
              f"{len(entry['way_ids'])} batiment(s)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export")
    e.add_argument("unit")
    e.add_argument("--note", default="", help="consigne libre ajoutee au prompt")
    e.add_argument("--force", action="store_true")

    i = sub.add_parser("import")
    i.add_argument("unit")
    i.add_argument("image", type=Path)
    i.add_argument("--allow-nonsquare", action="store_true")

    sub.add_parser("status")
    args = p.parse_args()

    index = load_index()
    if args.cmd == "export":
        export(args.unit, index, args.note, args.force)
    elif args.cmd == "import":
        import_drawing(args.unit, args.image, args.allow_nonsquare)
    else:
        status(index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
