#!/usr/bin/env python3
"""Mesure si un dessin au trait reste BLANC quand on le reduit.

    python scripts/ink_density.py assets/REF_02_castres.png

Le style vise est du noir sur blanc pur, sans aplat ni hachure. Le piege n'est pas
la quantite d'encre a taille reelle, c'est ce qu'elle devient a la reduction : une
texture fine (chaque tuile d'un toit, chaque pierre d'un quai) ne disparait pas en
retrecissant, elle s'agglomere en GRIS. C'est ce gris que l'on mesure ici.

Deux chiffres, pris apres reduction :
    encre    part de pixels franchement noirs        -> le trait
    gris     part de pixels ni noirs ni blancs       -> la texture agglomeree

C'est `gris` qui decide. Au-dela du seuil, la reference est trop dense pour
l'echelle de la carte et tirera tout le rendu vers le gris.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

INK_MAX = 60        # en dessous : du trait
PAPER_MIN = 235     # au dessus : du papier


def measure(img: Image.Image) -> tuple[float, float]:
    arr = np.asarray(img.convert("L"))
    ink = float((arr <= INK_MAX).mean())
    gray = float(((arr > INK_MAX) & (arr < PAPER_MIN)).mean())
    return ink, gray


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("images", nargs="+", type=Path)
    p.add_argument("--scale", type=float, default=0.15,
                   help="taux de reduction teste (0.15 = la taille d'une maison sur la carte)")
    p.add_argument("--max-gray", type=float, default=None,
                   help="part de gris toleree apres reduction (defaut : celle de --reference)")
    p.add_argument("--reference", type=Path, default=Path("assets/REF_01_style.png"),
                   help="image dont la densite sert de plafond quand --max-gray est absent")
    args = p.parse_args()

    # Le plafond n'est pas absolu : une tuile ou une reference est "trop dense"
    # si elle depasse la bible de style elle-meme. Mesure sur REF_01 : 51 %.
    if args.max_gray is None:
        if args.reference.exists():
            with Image.open(args.reference) as ref:
                small = ref.convert("L").resize((max(1, int(ref.width * args.scale)),
                                                 max(1, int(ref.height * args.scale))),
                                                Image.LANCZOS)
                args.max_gray = measure(small)[1] * 1.10
            print(f"plafond : {args.max_gray:.0%} de gris (110 % de {args.reference.name})")
        else:
            args.max_gray = 0.25

    worst = 0.0
    for path in args.images:
        with Image.open(path) as img:
            img = img.convert("L")
            full_ink, _ = measure(img)
            small = img.resize((max(1, int(img.width * args.scale)),
                                max(1, int(img.height * args.scale))), Image.LANCZOS)
            ink, gray = measure(small)
        worst = max(worst, gray)
        verdict = "OK" if gray <= args.max_gray else "TROP DENSE"
        print(f"{path.name:<32} {img.width}x{img.height}  "
              f"encre pleine taille {full_ink * 100:5.1f} %  |  a {args.scale:.0%} : "
              f"encre {ink * 100:5.1f} %  gris {gray * 100:5.1f} %  [{verdict}]")

    if worst > args.max_gray:
        print(f"\nPlus de {args.max_gray:.0%} de gris apres reduction : la texture "
              "s'agglomere au lieu de disparaitre. Alleger les toits et les pierres "
              "avant de se servir de cette image comme reference.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
