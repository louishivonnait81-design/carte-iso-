#!/usr/bin/env python3
"""Controle qualite des tuiles stylisees.

    python qa.py --tiles tiles/ --styled styled/ --out qa_out/

Deux mesures :
  * derive geometrique : contours Canny de la tuile stylisee compares a ceux du
    squelette Blender, apres flou leger ; rappel, precision et F1 par tuile.
  * raccords : bandes de 64 px de part et d'autre de chaque frontiere entre
    tuiles voisines ; concordance de l'encre au droit de la couture et ecart de
    densite entre les deux bandes.

Produit qa_out/report.html (vignettes + scores) et la liste des tuiles a refaire.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


# --------------------------------------------------------------------------
# Outils image
# --------------------------------------------------------------------------

def load_gray(path: Path, size: int | None = None) -> np.ndarray:
    with Image.open(path) as img:
        img = img.convert("L")
        if size and img.size != (size, size):
            img = img.resize((size, size), Image.LANCZOS)
        return np.asarray(img)


def edges(gray: np.ndarray, blur: int = 3, lo: int = 60, hi: int = 160) -> np.ndarray:
    if blur > 1:
        gray = cv2.GaussianBlur(gray, (blur | 1, blur | 1), 0)
    return cv2.Canny(gray, lo, hi) > 0


def ink(gray: np.ndarray, threshold: int = 200) -> np.ndarray:
    """Masque de l'encre : tout ce qui n'est pas le blanc du papier."""
    return gray < threshold


def thumb_b64(path: Path, size: int = 320) -> str:
    with Image.open(path) as img:
        img = img.convert("L")
        img.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# --------------------------------------------------------------------------
# Derive geometrique
# --------------------------------------------------------------------------

@dataclass
class Drift:
    tile: str
    recall: float        # part du squelette retrouvee dans la tuile stylisee
    precision: float     # part du dessin stylise adossee au squelette
    f1: float


def drift_score(skeleton: np.ndarray, styled: np.ndarray, tolerance_px: int) -> Drift:
    a, b = edges(skeleton), edges(styled)
    k = 2 * tolerance_px + 1
    kernel = np.ones((k, k), np.uint8)
    a_dil = cv2.dilate(a.astype(np.uint8), kernel) > 0
    b_dil = cv2.dilate(b.astype(np.uint8), kernel) > 0

    recall = float((a & b_dil).sum() / a.sum()) if a.sum() else 1.0
    precision = float((b & a_dil).sum() / b.sum()) if b.sum() else 0.0
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) else 0.0
    return Drift("", round(recall, 4), round(precision, 4), round(f1, 4))


# --------------------------------------------------------------------------
# Raccords
# --------------------------------------------------------------------------

@dataclass
class Seam:
    left: str
    right: str
    axis: str            # "vertical" (cote a cote) ou "horizontal" (l'un sur l'autre)
    edge_match: float    # concordance de l'encre au droit exact de la couture
    density_delta: float # ecart de densite d'encre entre les deux bandes de 64 px
    score: float


def seam_score(a_gray: np.ndarray, b_gray: np.ndarray, axis: str, band: int) -> Seam:
    """`a` est la tuile de gauche (axis=vertical) ou du haut (axis=horizontal)."""
    if axis == "horizontal":          # on ramene au cas vertical par rotation
        a_gray, b_gray = np.rot90(a_gray, -1), np.rot90(b_gray, -1)

    a_band, b_band = ink(a_gray[:, -band:]), ink(b_gray[:, :band])
    a_edge, b_edge = ink(a_gray[:, -1]), ink(b_gray[:, 0])

    union = a_edge | b_edge
    edge_match = float((a_edge & b_edge).sum() / union.sum()) if union.sum() else 1.0
    density_delta = float(abs(a_band.mean() - b_band.mean()))
    score = round(0.7 * edge_match + 0.3 * max(0.0, 1.0 - 8.0 * density_delta), 4)
    return Seam("", "", axis, round(edge_match, 4), round(density_delta, 4), score)


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------

CSS = """
body{font:14px/1.5 system-ui,sans-serif;margin:0;padding:24px;background:#fafaf8;color:#1a1a1a}
h1{font-size:22px;margin:0 0 4px} h2{font-size:16px;margin:28px 0 8px}
.meta{color:#666;margin-bottom:16px}
table{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 2px #0001}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums}
th{background:#f3f3f0;font-weight:600}
.bad{background:#fdecec} .warn{background:#fff7e6}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px;margin-top:10px}
.card{background:#fff;padding:8px;box-shadow:0 1px 2px #0001}
.card img{width:100%;display:block;background:#fff}
.card .n{font-size:12px;color:#555;margin-top:5px;display:flex;justify-content:space-between}
.redo{background:#fff;padding:12px;border-left:3px solid #c00;font-family:ui-monospace,monospace}
"""


def html_report(out: Path, drifts: list[Drift], seams: list[Seam], redo: list[str],
                cards: list[tuple[str, str]], thresholds: dict) -> Path:
    def row_class(value: float, low: float) -> str:
        return "bad" if value < low else ("warn" if value < low + 0.1 else "")

    drift_rows = "".join(
        f'<tr class="{row_class(d.f1, thresholds["drift"])}"><td>{d.tile}</td>'
        f"<td>{d.recall:.3f}</td><td>{d.precision:.3f}</td><td>{d.f1:.3f}</td></tr>"
        for d in sorted(drifts, key=lambda d: d.f1))
    seam_rows = "".join(
        f'<tr class="{row_class(s.score, thresholds["seam"])}"><td>{s.left} | {s.right}</td>'
        f"<td>{s.axis}</td><td>{s.edge_match:.3f}</td><td>{s.density_delta:.4f}</td>"
        f"<td>{s.score:.3f}</td></tr>"
        for s in sorted(seams, key=lambda s: s.score))
    card_html = "".join(
        f'<div class="card"><img src="data:image/png;base64,{b64}">'
        f'<div class="n"><span>{name}</span></div></div>' for name, b64 in cards)
    redo_html = ("<br>".join(redo) if redo else
                 "Aucune tuile sous les seuils : rien a regenerer.")

    path = out / "report.html"
    path.write_text(f"""<!doctype html><meta charset="utf-8">
<title>QA MicroMacro Castres</title><style>{CSS}</style>
<h1>Controle qualite des tuiles</h1>
<div class="meta">{len(drifts)} tuiles, {len(seams)} frontieres &middot;
seuil derive F1 &lt; {thresholds['drift']} &middot; seuil raccord &lt; {thresholds['seam']}</div>
<h2>Tuiles a regenerer</h2><div class="redo">{redo_html}</div>
<h2>Derive geometrique</h2>
<table><tr><th>tuile</th><th>rappel</th><th>precision</th><th>F1</th></tr>{drift_rows}</table>
<h2>Raccords</h2>
<table><tr><th>frontiere</th><th>axe</th><th>encre a la couture</th>
<th>ecart de densite</th><th>score</th></tr>{seam_rows}</table>
<h2>Vignettes</h2><div class="grid">{card_html}</div>
""", encoding="utf-8")
    return path


# --------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tiles", type=Path, default=Path("tiles"))
    p.add_argument("--styled", type=Path, default=Path("styled"))
    p.add_argument("--out", type=Path, default=Path("qa_out"))
    p.add_argument("--work-size", type=int, default=1024,
                   help="cote de travail pour la comparaison des contours")
    p.add_argument("--tolerance", type=int, default=4,
                   help="tolerance de recouvrement des contours, en pixels de travail")
    p.add_argument("--band", type=int, default=64, help="largeur de bande de raccord, en px")
    p.add_argument("--min-drift", type=float, default=0.55, help="seuil de F1 acceptable")
    p.add_argument("--min-seam", type=float, default=0.60, help="seuil de raccord acceptable")
    args = p.parse_args()

    index = json.loads((args.tiles / "index.json").read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)

    styled_paths = {t["name"]: args.styled / f"{t['name']}.png" for t in index["tiles"]}
    present = {n: p for n, p in styled_paths.items() if p.exists()}
    if not present:
        raise SystemExit(f"Aucune tuile stylisee dans {args.styled}.")
    print(f"[qa] {len(present)}/{len(styled_paths)} tuiles stylisees trouvees")

    drifts, cards = [], []
    for name, path in present.items():
        skeleton = load_gray(args.tiles / f"{name}.png", args.work_size)
        styled = load_gray(path, args.work_size)
        d = drift_score(skeleton, styled, args.tolerance)
        d = Drift(name, d.recall, d.precision, d.f1)
        drifts.append(d)
        cards.append((f"{name}  F1 {d.f1:.2f}", thumb_b64(path)))
        print(f"[qa] {name}: rappel {d.recall:.3f} precision {d.precision:.3f} F1 {d.f1:.3f}")

    seams = []
    by_name = {t["name"]: t for t in index["tiles"]}
    for name, tile in by_name.items():
        if name not in present:
            continue
        for side, axis in (("left", "vertical"), ("top", "horizontal")):
            other = tile["neighbours"].get(side)
            if not other or other not in present:
                continue
            a = load_gray(present[other], args.work_size)   # gauche ou haut
            b = load_gray(present[name], args.work_size)
            s = seam_score(a, b, axis, args.band)
            s = Seam(other, name, axis, s.edge_match, s.density_delta, s.score)
            seams.append(s)
            print(f"[qa] raccord {other} | {name} ({axis}): "
                  f"encre {s.edge_match:.3f} densite {s.density_delta:.4f} score {s.score:.3f}")

    bad = {d.tile for d in drifts if d.f1 < args.min_drift}
    bad |= {s.right for s in seams if s.score < args.min_seam}
    redo = sorted(bad)

    thresholds = {"drift": args.min_drift, "seam": args.min_seam}
    report = html_report(args.out, drifts, seams, redo, cards, thresholds)
    (args.out / "scores.json").write_text(json.dumps({
        "thresholds": thresholds,
        "drift": [asdict(d) for d in drifts],
        "seams": [asdict(s) for s in seams],
        "regenerate": redo,
    }, indent=2), encoding="utf-8")

    print(f"[qa] rapport : {report}")
    if redo:
        print("[qa] a regenerer : " + ",".join(redo))
        print("[qa]   python stylize.py --force --only " + ",".join(redo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
