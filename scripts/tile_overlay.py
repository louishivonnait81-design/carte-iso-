"""Grille de reperage sur une tuile, pour annoter a la main ce qu'OSM ignore.

    python scripts/tile_overlay.py --only tile_1_4

Une capture d'ecran de Google Maps n'est pas georeferencee : rien ne dit ou
commence ni ou finit la zone, ni a quelle echelle. Impossible d'en tirer une
position exploitable sans recalage manuel, tuile par tuile.

Il est bien plus simple que l'auteur regarde Google Maps d'un cote, la tuile
quadrillee de l'autre, et dise "une fontaine en C4". Cette grille rend cette
phrase traduisible en coordonnees Blender exactes : colonnes A a H de gauche a
droite, lignes 1 a 8 de haut en bas, dans le plan de l'image.
"""

from __future__ import annotations

import argparse
import json
import string
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DIVISIONS = 8


def font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_overlay(tile_png: Path, out: Path, divisions: int = DIVISIONS) -> None:
    with Image.open(tile_png) as img:
        base = img.convert("RGB")
    margin = 64
    canvas = Image.new("RGB", (base.width + margin, base.height + margin), "white")
    canvas.paste(base, (margin, margin))
    draw = ImageDraw.Draw(canvas)
    step = base.width / divisions
    label = font(34)

    for i in range(divisions + 1):
        x = margin + i * step
        y = margin + i * step
        colour = (150, 150, 150) if i % divisions else (60, 60, 60)
        draw.line((x, margin, x, canvas.height), fill=colour, width=2)
        draw.line((margin, y, canvas.width, y), fill=colour, width=2)
    for i in range(divisions):
        cx = margin + (i + 0.5) * step
        draw.text((cx - 12, 14), string.ascii_uppercase[i], fill=(180, 30, 30), font=label)
        draw.text((14, margin + (i + 0.5) * step - 18), str(i + 1),
                  fill=(180, 30, 30), font=label)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tiles", type=Path, default=ROOT / "tiles")
    p.add_argument("--out", type=Path, default=ROOT / "qa_out" / "reperage")
    p.add_argument("--only", help="tuiles precises, ex. 'tile_1_4,tile_1_5'")
    p.add_argument("--divisions", type=int, default=DIVISIONS)
    args = p.parse_args()

    index = json.loads((args.tiles / "index.json").read_text(encoding="utf-8"))
    wanted = set(args.only.split(",")) if args.only else None
    for name in index["render_order"]:
        if wanted and name not in wanted:
            continue
        source = args.tiles / f"{name}.png"
        if not source.exists():
            continue
        out = args.out / f"{name}_grille.png"
        draw_overlay(source, out, args.divisions)
        print(f"[reperage] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
