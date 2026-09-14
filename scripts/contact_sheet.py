"""Planche-contact des tuiles : voir toute la carte d'un coup avant de generer.

    python scripts/contact_sheet.py --source sem --out qa_out/planche_sem.png

Le gout du modele n'est pas le goulot d'etranglement, la justesse des donnees
l'est : une esplanade pietonne classee "rue" a fait dessiner une chaussee en
travers de la place Jean Jaures. Cette planche met les 28 tuiles cote a cote avec
leur nom pour reperer ce genre d'erreur avant de depenser une generation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def font(size: int):
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tiles", type=Path, default=Path("tiles"))
    p.add_argument("--styled", type=Path, default=Path("styled"))
    p.add_argument("--source", choices=["sem", "lines", "styled"], default="sem")
    p.add_argument("--cell", type=int, default=520, help="cote d'une vignette, en px")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    index = json.loads((args.tiles / "index.json").read_text(encoding="utf-8"))
    rows, cols = index["grid"]["rows"], index["grid"]["cols"]
    src, suffix = ((args.styled, "") if args.source == "styled"
                   else (args.tiles, "_sem" if args.source == "sem" else ""))

    cell, pad, label = args.cell, 6, 30
    sheet = Image.new("RGB", (cols * (cell + pad) + pad,
                              rows * (cell + pad + label) + pad), (235, 235, 232))
    draw = ImageDraw.Draw(sheet)
    small, missing = font(21), []

    for tile in index["tiles"]:
        x = pad + tile["col"] * (cell + pad)
        y = pad + tile["row"] * (cell + pad + label)
        path = src / f"{tile['name']}{suffix}.png"
        if path.exists():
            with Image.open(path) as img:
                sheet.paste(img.convert("RGB").resize((cell, cell), Image.LANCZOS), (x, y + label))
        else:
            missing.append(tile["name"])
            draw.rectangle((x, y + label, x + cell, y + label + cell), fill=(250, 240, 240))
            draw.text((x + cell // 2 - 40, y + label + cell // 2), "manquante",
                      fill=(190, 60, 60), font=small)
        draw.text((x + 2, y + 6), f"{tile['row']}_{tile['col']}", fill=(60, 60, 60), font=small)

    out = args.out or Path("qa_out") / f"planche_{args.source}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"[planche] {out}  {sheet.width}x{sheet.height}"
          + (f"  ({len(missing)} manquantes)" if missing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
