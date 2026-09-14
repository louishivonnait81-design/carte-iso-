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
    "anchor": "tuile deja validee — style a reproduire",
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

3. VERIFIER QUE L'IMAGE RENDUE EST CARREE. L'interface web ignore souvent la
   consigne "output square" et renvoie du 16:9 : une tuile non carree ne
   correspond plus au squelette Blender, la geometrie derive et les raccords
   sautent. Si elle ne l'est pas, regenerer en imposant le format 1:1.

4. Telecharger l'image produite, puis :
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
                sections: dict, use_ref02: bool, water: str, force: bool,
                use_ref01: bool = True, anchor=None) -> Path:
    job = stylize.build_job(tile, tiles, styled, sections, use_ref02, water,
                            stylize.load_notes(tiles), use_ref01=use_ref01, anchor=anchor)
    folder = out / tile["name"]
    if folder.exists():
        if not force:
            sys.exit(f"{folder} existe deja : --force pour la refaire.")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    # plusieurs roles peuvent pointer la meme image : un seul fichier, plusieurs
    # mentions dans le mode d'emploi
    names: dict[int, str] = {}
    for role, num in zip(job.roles, job.numbers):
        names.setdefault(num, role)
    lines, written = [], {}
    for num, src in enumerate(job.images, start=1):
        dest = folder / f"{num}_{names[num]}.png"
        shutil.copyfile(src, dest)
        written[num] = dest.name
    for role, num in zip(job.roles, job.numbers):
        lines.append(f"     image {num} : {written[num]:<16} {ROLE_LABELS[role]}")

    (folder / "prompt.txt").write_text(job.prompt + "\n", encoding="utf-8")
    # empreinte des entrees : permet de reperer plus tard une tuile devenue
    # perimee parce qu'une voisine a ete refaite depuis
    (folder / "job.json").write_text(json.dumps(
        {"tile": tile["name"], "roles": job.roles,
         "cache_key": job.cache_key("manuel", "1:1", "-")}, indent=2), encoding="utf-8")
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
                    args.use_ref02, args.water, args.force, args.ref01 == "on",
                    stylize.resolve_anchor(args.anchor, args.styled))

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

    with Image.open(src) as img:
        img = img.convert("RGB")
        size = (img.width, img.height)
        if img.width != img.height and not args.allow_nonsquare:
            sys.exit(
                f"Image NON CARREE : {img.width}x{img.height}.\n"
                "L'interface web ignore souvent la consigne 'output square'. Une tuile\n"
                "non carree ne correspond plus au squelette Blender : la geometrie derive\n"
                "et tous les raccords sautent. Regenerer en demandant explicitement un\n"
                "format 1:1 dans l'interface, ou passer par l'API (--aspect-ratio 1:1).\n"
                "Pour passer outre en connaissance de cause : --allow-nonsquare."
            )
        args.styled.mkdir(parents=True, exist_ok=True)
        img.save(dest, "PNG")
    if size[0] != size[1]:
        print(f"[import] ATTENTION : tuile non carree {size[0]}x{size[1]} acceptee de force.")
    job_file = args.out / args.tile / "job.json"
    if job_file.exists():
        meta = json.loads(job_file.read_text(encoding="utf-8"))
        (args.styled / f"{args.tile}.json").write_text(json.dumps(meta, indent=2),
                                                       encoding="utf-8")
    print(f"[import] {src.name} -> {dest}  {size[0]}x{size[1]}")
    return 0


def stale_tiles(args, index, sections) -> set[str]:
    """Tuiles dont une entree a change depuis leur generation.

    Refaire une tuile change l'image de continuite de ses voisines droite et
    basse : elles ont ete dessinees d'apres une version qui n'existe plus. Sans
    ce controle, l'incoherence ne se voit qu'a l'assemblage final.
    """
    tiles = {t["name"]: t for t in index["tiles"]}
    notes = stylize.load_notes(args.tiles)
    anchor = stylize.resolve_anchor(args.anchor, args.styled)
    stale = set()
    for name in index["render_order"]:
        meta_path = args.styled / f"{name}.json"
        if not (args.styled / f"{name}.png").exists() or not meta_path.exists():
            continue
        try:
            job = stylize.build_job(tiles[name], args.tiles, args.styled, sections,
                                    args.use_ref02, args.water, notes,
                                    use_ref01=args.ref01 == "on", anchor=anchor)
        except SystemExit:
            continue
        recorded = json.loads(meta_path.read_text(encoding="utf-8")).get("cache_key")
        if recorded and recorded != job.cache_key("manuel", "1:1", "-"):
            stale.add(name)
    return stale


def cmd_status(args, index, sections) -> int:
    rows, cols = index["grid"]["rows"], index["grid"]["cols"]
    order = index["render_order"]
    done = {n for n in order if (args.styled / f"{n}.png").exists()}
    stale = stale_tiles(args, index, sections) & done

    print(f"[status] {len(done)}/{len(order)} tuiles stylisees"
          + (f", dont {len(stale)} perimees" if stale else "") + "\n")
    for r in range(rows):
        cells = []
        for c in range(cols):
            n = f"tile_{r}_{c}"
            cells.append("!!" if n in stale else ("##" if n in done else ".."))
        print("   " + " ".join(cells))
    print("\n   ## faite   !! perimee (une entree a change depuis)   .. a faire")
    remaining = [n for n in order if n not in done]
    print(f"   prochaine : {remaining[0] if remaining else '— terminé'}")
    if stale:
        print("   a refaire : " + ",".join(sorted(stale)))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tiles", type=Path, default=ROOT / "tiles")
    p.add_argument("--styled", type=Path, default=ROOT / "styled")
    p.add_argument("--out", type=Path, default=ROOT / "manual")
    p.add_argument("--water", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--ref02", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--ref01", choices=["on", "off"], default="on",
                   help="'off' : REF_02 seule porte le style de trait")
    p.add_argument("--anchor", default=None, metavar="TUILE",
                   help="tuile deja validee servant de reference de style")
    p.add_argument("--force", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    # --force est utile avant comme apres la sous-commande ; SUPPRESS evite que le
    # defaut du sous-parseur n'ecrase la valeur donnee en tete de ligne
    def add_force(parser):
        parser.add_argument("--force", action="store_true", default=argparse.SUPPRESS)

    export = sub.add_parser("export", help="preparer une ou des tuiles")
    export.add_argument("--only", help="tuiles precises, ex. 'tile_0_0,tile_0_1'")
    export.add_argument("--all", action="store_true", help="toute la grille")
    add_force(export)
    add_force(sub.add_parser("next", help="preparer la prochaine tuile non stylisee"))
    imp = sub.add_parser("import", help="reimporter une image produite par Gemini")
    imp.add_argument("tile")
    imp.add_argument("file")
    imp.add_argument("--allow-nonsquare", action="store_true",
                     help="accepter une tuile non carree (casse la geometrie)")
    add_force(imp)
    sub.add_parser("status", help="avancement")

    args = p.parse_args()
    if args.cmd == "import":
        return cmd_import(args)

    index = load_index(args.tiles)
    args.use_ref02 = args.ref02 == "on" or (args.ref02 == "auto" and stylize.REF02.exists())
    if args.ref02 == "on" and not stylize.REF02.exists():
        sys.exit(f"--ref02 on mais {stylize.REF02} est absent.")
    if args.ref01 == "on" and not args.anchor and not stylize.REF01.exists():
        sys.exit(f"Reference de style manquante : {stylize.REF01}")

    sections = stylize.load_sections(stylize.PROMPT)
    if args.cmd == "status":
        return cmd_status(args, index, sections)
    if args.cmd == "next":
        args.all, args.only = False, None
    return cmd_export(args, index, sections)


if __name__ == "__main__":
    raise SystemExit(main())
