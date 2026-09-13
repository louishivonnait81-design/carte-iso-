#!/usr/bin/env python3
"""Vue cote a cote de deux tuiles voisines, frontiere marquee.

    python scripts/seam_preview.py --styled styled/ --pair tile_0_0 tile_0_1 \
        --out qa_out/seam_0_0-0_1.png

Sert a juger un raccord a l'oeil avant de lancer la grille complete : les deux
tuiles collees, un trait rouge sur la couture, et un agrandissement de la bande
de 128 px de part et d'autre.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--styled", type=Path, default=Path("styled"))
    p.add_argument("--pair", nargs=2, metavar=("A", "B"), required=True,
                   help="tuile de gauche (ou du haut) puis tuile de droite (ou du bas)")
    p.add_argument("--axis", choices=["vertical", "horizontal"], default="vertical",
                   help="vertical = A a gauche de B ; horizontal = A au-dessus de B")
    p.add_argument("--band", type=int, default=128, help="demi-largeur du zoom, en px")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-px", type=int, default=1600, help="cote max de chaque tuile affichee")
    args = p.parse_args()

    paths = [args.styled / f"{n}.png" for n in args.pair]
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Tuile introuvable : {path}")

    imgs = []
    for path in paths:
        with Image.open(path) as img:
            img = img.convert("L")
            if max(img.size) > args.max_px:
                img = img.resize((args.max_px, args.max_px), Image.LANCZOS)
            imgs.append(img.copy())
    a, b = imgs
    w, h = a.size

    if args.axis == "vertical":
        pair = Image.new("L", (2 * w, h), 255)
        pair.paste(a, (0, 0)); pair.paste(b, (w, 0))
        seam = (w, 0, w, h)
        crop = pair.crop((w - args.band, 0, w + args.band, h))
        zoom = crop.resize((crop.width * 3, min(h, crop.height * 3 // 1)), Image.LANCZOS)
    else:
        pair = Image.new("L", (w, 2 * h), 255)
        pair.paste(a, (0, 0)); pair.paste(b, (0, h))
        seam = (0, h, w, h)
        crop = pair.crop((0, h - args.band, w, h + args.band))
        zoom = crop.resize((crop.width, crop.height * 3), Image.LANCZOS)

    canvas = Image.new("RGB", (max(pair.width, zoom.width), pair.height + zoom.height + 12), "white")
    canvas.paste(pair.convert("RGB"), (0, 0))
    canvas.paste(zoom.convert("RGB"), (0, pair.height + 12))

    draw = ImageDraw.Draw(canvas)
    draw.line(seam, fill=(220, 30, 30), width=3)
    if args.axis == "vertical":
        x = args.band * (zoom.width / crop.width)
        draw.line((x, pair.height + 12, x, canvas.height), fill=(220, 30, 30), width=3)
    else:
        y = pair.height + 12 + args.band * (zoom.height / crop.height)
        draw.line((0, y, canvas.width, y), fill=(220, 30, 30), width=3)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out)
    print(f"[seam] {args.pair[0]} | {args.pair[1]} -> {args.out}  {canvas.width}x{canvas.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
