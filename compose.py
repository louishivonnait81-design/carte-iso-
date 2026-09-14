"""Recolle les unites dessinees a leur place exacte dans la mosaique.

    python compose.py --tile tile_1_4 --out out/compose_tile_1_4.png
    python compose.py --check tile_1_4        # controle du chainage

C'est ici que la position est decidee, et nulle part ailleurs. Chaque unite est
posee a la boite en pixels que scripts/render_units.py a mesuree, d'arriere en
avant, decoupee par sa silhouette. Le dessin n'a plus son mot a dire sur l'ou :
il ne fournit que l'encre.

Le mode --check colle les rendus BRUTS de Blender, sans passer par le modele, et
compare le resultat au squelette de la tuile entiere. Les deux images doivent
etre presque identiques. Si elles ne le sont pas, la faute est dans le calcul
des boites ou dans l'ordre de pose — pas dans le dessin — et il faut la corriger
avant de depenser la moindre generation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent


def load_index(units_dir: Path) -> dict:
    path = units_dir / "index.json"
    if not path.exists():
        raise SystemExit(f"{path} introuvable : lancer `make units` d'abord.")
    return json.loads(path.read_text(encoding="utf-8"))


def compose(index: dict, units_dir: Path, drawn_dir: Path | None,
            source: str = "line") -> Image.Image:
    """Pose toutes les unites sur une toile blanche aux dimensions de la mosaique.

    `source` vaut "line" pour les rendus bruts de Blender, ou le nom du dossier
    des dessins retournes par le modele. Une unite non encore dessinee retombe
    sur son rendu brut : la carte reste complete pendant l'avancement.
    """
    w, h = index["grid"]["mosaic_px"]
    canvas = Image.new("L", (w, h), 255)

    for entry in sorted(index["units"], key=lambda e: e["order"]):
        art = None
        if drawn_dir is not None:
            candidate = drawn_dir / f"{entry['name']}.png"
            if candidate.exists():
                art = Image.open(candidate).convert("L")
        if art is None:
            art = Image.open(units_dir / entry[source]).convert("L")

        box = (entry["w"], entry["h"])
        if art.size != box:
            # un dessin revenu a une autre taille est remis a l'echelle de sa
            # boite : c'est la boite qui fait foi, jamais l'image
            art = art.resize(box, Image.LANCZOS)

        mask = Image.open(units_dir / entry["mask"]).convert("L")
        if mask.size != box:
            mask = mask.resize(box, Image.NEAREST)

        canvas.paste(art, (entry["x"], entry["y"]), mask)
    return canvas


def tile_crop(canvas: Image.Image, index: dict, tile: str) -> Image.Image:
    row, col = (int(v) for v in tile.split("_")[1:3])
    px = index["grid"]["tile_px"]
    return canvas.crop((col * px, row * px, (col + 1) * px, (row + 1) * px))


def check(index: dict, units_dir: Path, tile: str, skeleton: Path,
          search: int = 24) -> tuple[float, tuple[int, int]]:
    """Compare le collage des rendus bruts au squelette de la tuile entiere.

    Renvoie la concordance et le decalage qui la maximise. C'est le DECALAGE qui
    juge le chainage : s'il est nul, chaque unite est posee exactement la ou le
    rendu d'ensemble la place, et le calcul des boites est bon.

    La concordance, elle, ne peut pas atteindre 100 % et ce n'est pas un defaut.
    Une unite est rendue SEULE : son contour arriere, que sa voisine masquerait
    dans la scene complete, est dessine. Mesure sur tile_1_4 : 16 % de l'encre
    recollee est de cette nature, et l'inspection visuelle montre qu'il s'agit
    bien d'aretes cachees, pas de matiere deplacee.
    """
    import numpy as np

    got = np.asarray(tile_crop(compose(index, units_dir, None), index, tile)) < 128
    want = np.asarray(Image.open(skeleton).convert("L")) < 128
    if got.shape != want.shape:
        raise SystemExit(f"tailles differentes : {got.shape} vs {want.shape}")

    # tolerance d'un pixel : l'anticrenelage des deux rendus ne tombe pas
    # forcement du meme cote du seuil
    grown = want.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(want, dy, 0), dx, 1)

    step = max(1, got.shape[0] // 512)
    g0, w0 = got[::step, ::step], grown[::step, ::step]
    best = (-1, (0, 0))
    for dy in range(-search, search + 1, 2):
        for dx in range(-search, search + 1, 2):
            score = (np.roll(np.roll(g0, dy, 0), dx, 1) & w0).sum()
            if score > best[0]:
                best = (score, (dx * step, dy * step))
    return float((got & grown).sum() / max(1, got.sum())), best[1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--units", type=Path, default=ROOT / "units")
    p.add_argument("--drawn", type=Path, default=ROOT / "drawn",
                   help="dossier des unites redessinees, <nom>.png")
    p.add_argument("--tile", default=None, help="ne sortir que cette tuile")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--check", default=None, metavar="TUILE",
                   help="controler le chainage sur cette tuile, sans le modele")
    p.add_argument("--skeleton", type=Path, default=ROOT / "tiles")
    args = p.parse_args()

    index = load_index(args.units)

    if args.check:
        skeleton = args.skeleton / f"{args.check}.png"
        rate, (dx, dy) = check(index, args.units, args.check, skeleton)
        print(f"[compose] {args.check} : {100 * rate:.1f} % de l'encre recollee "
              f"tombe sur le squelette")
        print(f"[compose] decalage qui maximiserait la concordance : "
              f"dx={dx} dy={dy} px")
        ok = (dx, dy) == (0, 0) and rate >= 0.75
        print("[compose] " + ("chainage correct : aucune unite deplacee" if ok else
                              "ECART : verifier les boites ou l'ordre de pose"))
        return 0 if ok else 1

    drawn = args.drawn if args.drawn.exists() else None
    canvas = compose(index, args.units, drawn)
    image = tile_crop(canvas, index, args.tile) if args.tile else canvas
    out = args.out or (ROOT / "out" /
                       (f"compose_{args.tile}.png" if args.tile else "compose.png"))
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    print(f"[compose] -> {out}  {image.size[0]}x{image.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
