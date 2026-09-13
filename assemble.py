#!/usr/bin/env python3
"""Assemblage de la carte complete et vectorisation.

    python assemble.py --styled styled/ --out out/

Produit :
    out/castres_map.png   mosaique pleine resolution (calque decor)
    out/castres_map.svg   vectorisation en un seul calque
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None      # la carte finale depasse la limite anti-bombe


def build_mosaic(index: dict, src: Path, suffix: str, missing: str) -> Image.Image:
    rows, cols = index["grid"]["rows"], index["grid"]["cols"]
    px = index["tile"]["pixels"]
    canvas = Image.new("RGB", (cols * px, rows * px), "white")   # RGB : la mosaique
    # semantique garde ses couleurs ; les tuiles stylisees sont de toute facon en noir et blanc

    absent = []
    for tile in index["tiles"]:
        path = src / f"{tile['name']}{suffix}.png"
        if not path.exists():
            absent.append(tile["name"])
            continue
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.size != (px, px):
                img = img.resize((px, px), Image.LANCZOS)
            canvas.paste(img, (tile["col"] * px, tile["row"] * px))

    if absent:
        message = f"{len(absent)} tuiles manquantes : {', '.join(absent[:8])}" \
                  + (" ..." if len(absent) > 8 else "")
        if missing == "error":
            raise SystemExit(message + "\nUtiliser --missing blank pour assembler quand meme.")
        print(f"[assemble] ATTENTION : {message} (laissees en blanc)")
    return canvas


def binarise(img: Image.Image, threshold: int) -> Image.Image:
    return img.point(lambda v: 0 if v < threshold else 255, mode="L")


def vectorise(png: Path, svg: Path, engine: str, threshold: int, max_px: int) -> str:
    """Vectorise en un calque unique. vtracer par defaut, potrace en repli."""
    with Image.open(png) as img:
        img = img.convert("L")
        if max(img.size) > max_px:
            scale = max_px / max(img.size)
            new = (int(img.width * scale), int(img.height * scale))
            print(f"[assemble] reduction avant vectorisation : {img.size} -> {new} "
                  f"(--vector-max-px pour changer)")
            img = img.resize(new, Image.LANCZOS)
        flat = binarise(img, threshold)

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "flat.png"
        flat.save(source)

        if engine in ("vtracer", "auto"):
            try:
                import vtracer
            except ImportError:
                if engine == "vtracer":
                    raise SystemExit("vtracer absent : pip install vtracer")
            else:
                vtracer.convert_image_to_svg_py(
                    str(source), str(svg), colormode="binary", mode="spline",
                    hierarchical="cutout", filter_speckle=4, corner_threshold=60,
                    path_precision=3)
                return "vtracer"

        if shutil.which("potrace") is None:
            raise SystemExit("Ni vtracer ni potrace disponibles pour la vectorisation.")
        pbm = Path(tmp) / "flat.pbm"
        flat.convert("1").save(pbm)
        subprocess.check_call(["potrace", "-s", "-o", str(svg), str(pbm)])
        return "potrace"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tiles", type=Path, default=Path("tiles"), help="dossier des squelettes")
    p.add_argument("--styled", type=Path, default=Path("styled"), help="dossier des tuiles finies")
    p.add_argument("--out", type=Path, default=Path("out"))
    p.add_argument("--source", choices=["styled", "lines", "sem"], default="styled",
                   help="quelles tuiles assembler")
    p.add_argument("--name", default="castres_map")
    p.add_argument("--missing", choices=["blank", "error"], default="blank")
    p.add_argument("--no-svg", action="store_true", help="ne produire que le PNG")
    p.add_argument("--engine", choices=["auto", "vtracer", "potrace"], default="auto")
    p.add_argument("--threshold", type=int, default=170,
                   help="seuil noir/blanc avant vectorisation")
    p.add_argument("--vector-max-px", type=int, default=8000,
                   help="cote maximal envoye au vectoriseur")
    args = p.parse_args()

    index = json.loads((args.tiles / "index.json").read_text(encoding="utf-8"))
    src, suffix = {
        "styled": (args.styled, ""),
        "lines": (args.tiles, ""),
        "sem": (args.tiles, "_sem"),
    }[args.source]

    args.out.mkdir(parents=True, exist_ok=True)
    png = args.out / f"{args.name}.png"

    mosaic = build_mosaic(index, src, suffix, args.missing)
    mosaic.save(png, optimize=True)
    print(f"[assemble] PNG : {png}  {mosaic.width}x{mosaic.height}")

    if not args.no_svg:
        svg = args.out / f"{args.name}.svg"
        engine = vectorise(png, svg, args.engine, args.threshold, args.vector_max_px)
        print(f"[assemble] SVG : {svg}  ({engine}, calque unique 'decor')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
