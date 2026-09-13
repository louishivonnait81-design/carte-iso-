#!/usr/bin/env python3
"""Mode manuel : preparer les copier-coller pour Gemini, puis reimporter.

Aucun appel API. Le reste du pipeline (qa.py, assemble.py) fonctionne ensuite
normalement puisque les tuiles finies atterrissent dans styled/ sous leur vrai nom.

    python manual.py next                       # prepare la prochaine tuile a faire
    python manual.py export --only tile_0_0     # prepare une tuile precise
    python manual.py export --all               # prepare tout ce qui est faisable
    python manual.py import tile_0_0 ~/Downloads/gemini.png
    python manual.py status                     # ou en est-on

`export` cree manual/<tuile>/ contenant :
    prompt.txt        le texte a coller
    1_*.png 2_*.png   les images a televerser, DANS CET ORDRE
    LISEZMOI.txt      le mode d'emploi de la tuile
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

import stylize  # noqa: E402

ROOT = Path(__file__).resolve().parent

ROLE_LABELS = {
    "ref01": "REF_01 — style de trait",
    "ref02": "REF_02 — architecture castraise",
    "lines": "tuile lignes (squelette Blender)",
    "sem": "tuile semantique (aplats)",
    "left": "voisine de GAUCHE, deja stylisee",
    "top": "voisine du HAUT, deja stylisee",
}

NOTICE = """Tuile {name}

1. Ouvrir Gemini et televerser les {n} images DANS CET ORDRE :
{listing}

2. Coller le contenu de prompt.txt.

3. Telecharger l'image produite, puis :
     python manual.py import {name} <fichier telecharge>

L'ordre des images est ce qui fait tenir le prompt : il y est fait reference par
numero ("image 2", "image 4"...). Une image intervertie casse le resultat.
"""


def load_index(tiles: Path) -> dict:
    path = tiles / "index.json"
    if not path.exists():
        sys.exit(f"{path} introuvable : lancer `make render` d'abord.")
    return json.loads(path.read_text(encoding="utf-8"))


def export_tile(tile: dict, tiles: Path, styled: Path, out: Path,
                sections: dict, use_ref02: bool, water: str, force: bool) -> Path:
    job = stylize.build_job(tile, tiles, styled, sections, use_ref02, water)
    folder = out / tile["name"]
    if folder.exists():
        if not force:
            sys.exit(f"{folder} existe deja : --force pour la refaire.")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    lines = []
    for i, (role, src) in enumerate(zip(job.roles, job.images), start=1):
        dest = folder / f"{i}_{role}.png"
        shutil.copyfile(src, dest)
        lines.append(f"     image {i} : {dest.name:<14} {ROLE_LABELS[role]}")

    (folder / "prompt.txt").write_text(job.prompt + "\n", encoding="utf-8")
    (folder / "LISEZMOI.txt").write_text(
        NOTICE.format(name=tile["name"], n=len(job.images), listing="\n".join(lines)),
        encoding="utf-8")

    print(f"[export] {folder}  ({len(job.images)} images)")
    for line in lines:
        print(line)
    return folder


def cmd_export(args, index, sections) -> int:
    tiles = {t["name"]: t for t in index["tiles"]}
    if args.all:
        names = list(index["render_order"])
    elif args.only:
        names = args.only.split(",")
    else:
        names = [n for n in index["render_order"]
                 if not (args.styled / f"{n}.png").exists()][:1]
        if not names:
            print("[export] toutes les tuiles sont deja stylisees.")
            return 0

    for name in names:
        if name not in tiles:
            sys.exit(f"Tuile inconnue : {name}")
        export_tile(tiles[name], args.tiles, args.styled, args.out, sections,
                    args.use_ref02, args.water, args.force)

    if not args.all and len(names) == 1:
        print(f"\nSuivre {args.out / names[0] / 'LISEZMOI.txt'}")
    elif args.all:
        print("\nNote : les tuiles exportees en bloc n'ont pas leurs voisines "
              "stylisees. Pour la continuite, faire tuile par tuile avec "
              "`python manual.py next`.")
    return 0


def cmd_import(args) -> int:
    from PIL import Image

    src = Path(args.file).expanduser()
    if not src.exists():
        sys.exit(f"Fichier introuvable : {src}")
    dest = args.styled / f"{args.tile}.png"
    if dest.exists() and not args.force:
        sys.exit(f"{dest} existe deja : --force pour remplacer.")

    args.styled.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = img.convert("RGB")
        if img.width != img.height:
            print(f"[import] ATTENTION : image non carree ({img.width}x{img.height}). "
                  "Gemini a du recadrer — le raccord risque d'etre decale.")
        img.save(dest, "PNG")
    print(f"[import] {src.name} -> {dest}  {img.width}x{img.height}")
    return 0


def cmd_status(args, index) -> int:
    rows, cols = index["grid"]["rows"], index["grid"]["cols"]
    done = {n for n in index["render_order"] if (args.styled / f"{n}.png").exists()}
    print(f"[status] {len(done)}/{len(index['render_order'])} tuiles stylisees\n")
    for r in range(rows):
        print("   " + " ".join("##" if f"tile_{r}_{c}" in done else ".." for c in range(cols)))
    remaining = [n for n in index["render_order"] if n not in done]
    print(f"\n   prochaine : {remaining[0] if remaining else '— terminé'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tiles", type=Path, default=ROOT / "tiles")
    p.add_argument("--styled", type=Path, default=ROOT / "styled")
    p.add_argument("--out", type=Path, default=ROOT / "manual")
    p.add_argument("--water", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--ref02", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--force", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    export = sub.add_parser("export", help="preparer une ou des tuiles")
    export.add_argument("--only", help="tuiles precises, ex. 'tile_0_0,tile_0_1'")
    export.add_argument("--all", action="store_true", help="toute la grille")
    sub.add_parser("next", help="preparer la prochaine tuile non stylisee")
    imp = sub.add_parser("import", help="reimporter une image produite par Gemini")
    imp.add_argument("tile")
    imp.add_argument("file")
    sub.add_parser("status", help="avancement")

    args = p.parse_args()
    if args.cmd == "import":
        return cmd_import(args)

    index = load_index(args.tiles)
    if args.cmd == "status":
        return cmd_status(args, index)

    args.use_ref02 = args.ref02 == "on" or (args.ref02 == "auto" and stylize.REF02.exists())
    if args.ref02 == "on" and not stylize.REF02.exists():
        sys.exit(f"--ref02 on mais {stylize.REF02} est absent.")
    if not stylize.REF01.exists():
        sys.exit(f"Reference de style manquante : {stylize.REF01}")

    sections = stylize.load_sections(stylize.PROMPT)
    if args.cmd == "next":
        args.all, args.only = False, None
    return cmd_export(args, index, sections)


if __name__ == "__main__":
    raise SystemExit(main())
