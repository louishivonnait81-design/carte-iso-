"""Annotations a la main : ce que l'observation ajoute a OpenStreetMap.

OSM ne cartographie pas tout. La terrasse surelevee autour de la statue de Jean
Jaures, les jardinieres de la place, l'etendue exacte d'un pavement : rien de
cela n'y figure, alors que ces elements se voient d'un coup d'oeil sur une vue
aerienne. Ce module permet de les ajouter en les designant sur la grille de
reperage produite par tile_overlay.py — "une fontaine en C4" — plutot qu'en
inventant des coordonnees.

Format de assets/annotations.json :

    {
      "tile_1_4": [
        {"kind": "terrace", "at": "F6", "size": [8, 5], "note": "socle de la statue"},
        {"kind": "planter", "at": ["E6", "F6"]},
        {"kind": "fountain", "at": "C4"}
      ]
    }

`at` est une case de la grille, ou une paire de cases pour un element etire.
Tout ce qui vient d'ici est marque confiance 0,6 : vu, pas mesure.
"""

from __future__ import annotations

import json
import string
from dataclasses import dataclass
from pathlib import Path

from geo import TileGrid, unproject_to_ground, xy_to_latlon

DIVISIONS = 8
CONFIDENCE = 0.6

# Volume associe a chaque type. hauteur 0 = dalle posee au sol.
KINDS = {
    "terrace":  {"shape": "slab", "size": (8.0, 5.0), "height": 0.18},
    "planter":  {"shape": "slab", "size": (2.0, 1.0), "height": 0.55},
    "fountain": {"shape": "basin", "size": (3.6, 3.6), "height": 0.80},
    "statue":   {"shape": "plinth", "size": (1.5, 1.5), "height": 2.2},
    "kiosk":    {"shape": "box", "size": (2.5, 2.5), "height": 2.8},
    "stall":    {"shape": "box", "size": (3.0, 2.0), "height": 2.4},
    "wall":     {"shape": "slab", "size": (6.0, 0.4), "height": 0.9},
    "steps":    {"shape": "slab", "size": (4.0, 1.5), "height": 0.35},
}


class AnnotationError(ValueError):
    pass


@dataclass(frozen=True)
class Annotation:
    tile: str
    kind: str
    x: float          # coordonnees Blender
    y: float
    size: tuple[float, float]
    height: float
    shape: str
    note: str = ""


def cell_centre(cell: str, divisions: int = DIVISIONS) -> tuple[float, float]:
    """Case 'C4' -> position relative dans la tuile, de 0 a 1 (x vers la droite,
    y vers le bas)."""
    cell = cell.strip().upper()
    if len(cell) < 2 or cell[0] not in string.ascii_uppercase[:divisions]:
        raise AnnotationError(f"Case invalide : {cell!r} (attendu A1 a "
                              f"{string.ascii_uppercase[divisions - 1]}{divisions})")
    try:
        row = int(cell[1:])
    except ValueError as exc:
        raise AnnotationError(f"Case invalide : {cell!r}") from exc
    if not 1 <= row <= divisions:
        raise AnnotationError(f"Ligne hors grille : {cell!r}")
    col = string.ascii_uppercase.index(cell[0])
    return ((col + 0.5) / divisions, (row - 0.5) / divisions)


def to_world(tile_name: str, cells, grid: TileGrid, divisions: int = DIVISIONS):
    """Case(s) de la grille -> point au sol, en coordonnees Blender."""
    tile = next((t for t in grid.tiles() if t.name == tile_name), None)
    if tile is None:
        raise AnnotationError(f"Tuile inconnue : {tile_name}")
    cells = [cells] if isinstance(cells, str) else list(cells)
    points = []
    for cell in cells:
        fx, fy = cell_centre(cell, divisions)
        su = tile.screen_center[0] + (fx - 0.5) * grid.tile_m
        sv = tile.screen_center[1] - (fy - 0.5) * grid.tile_m
        p = unproject_to_ground(su, sv, grid.target, grid.basis, grid.ground_z)
        points.append((p[0], p[1]))
    return (sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points))


def load(path: Path, grid: TileGrid, divisions: int = DIVISIONS) -> list[Annotation]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for tile_name, entries in data.items():
        if tile_name.startswith("_"):
            continue
        for entry in entries:
            kind = entry.get("kind")
            if kind not in KINDS:
                raise AnnotationError(
                    f"{tile_name} : type inconnu {kind!r}. Connus : {sorted(KINDS)}")
            spec = KINDS[kind]
            x, y = to_world(tile_name, entry["at"], grid, divisions)
            out.append(Annotation(
                tile=tile_name, kind=kind, x=x, y=y,
                size=tuple(entry.get("size", spec["size"])),
                height=float(entry.get("height", spec["height"])),
                shape=spec["shape"], note=entry.get("note", "")))
    return out


def describe(annotations: list[Annotation], grid: TileGrid) -> list[dict]:
    """Provenance, pour le fichier de confiance."""
    return [{"tile": a.tile, "kind": a.kind, "note": a.note,
             "latlon": list(xy_to_latlon(a.x, a.y, grid.origin_lat, grid.origin_lon)),
             "source": "annotation", "confidence": CONFIDENCE}
            for a in annotations]
