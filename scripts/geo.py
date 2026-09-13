"""Geometrie de la grille de tuiles isometriques.

Python pur, SANS bpy : ce module est importable depuis Blender comme depuis un
interpreteur CPython normal, ce qui permet de tester la projection lat/lon et le
decoupage en tuiles sans installer Blender.

Conventions
-----------
* Projection equirectangulaire locale, centree sur l'origine de scene Blosm
  (scene["lat"], scene["lon"]). Precision largement suffisante sur ~1 km.
* Camera orthographique, elevation 30 deg au-dessus de l'horizon, azimut 45 deg.
  Dans Blender : rotation_euler = (radians(90 - elevation), 0, radians(azimuth)),
  ordre XYZ, camera qui regarde selon son -Z local.
* La grille de tuiles est definie dans le PLAN IMAGE (ecran), pas dans le plan
  du sol : une tuile de 180 m fait 180 m de large a l'ecran. Le tuilage se fait
  par cam.shift_x / cam.shift_y, en unites de largeur de cadre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Metres par degre, projection equirectangulaire locale (cf. cahier des charges).
M_PER_DEG_LAT = 110540.0
M_PER_DEG_LON = 111320.0

Vec3 = tuple[float, float, float]


# --------------------------------------------------------------------------
# Projection lat/lon <-> coordonnees Blender
# --------------------------------------------------------------------------

def latlon_to_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Convertit lat/lon (degres) en coordonnees Blender (metres) autour de lat0/lon0."""
    x = (lon - lon0) * M_PER_DEG_LON * math.cos(math.radians(lat0))
    y = (lat - lat0) * M_PER_DEG_LAT
    return x, y


def xy_to_latlon(x: float, y: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Inverse de :func:`latlon_to_xy`."""
    lat = lat0 + y / M_PER_DEG_LAT
    lon = lon0 + x / (M_PER_DEG_LON * math.cos(math.radians(lat0)))
    return lat, lon


# --------------------------------------------------------------------------
# Repere camera
# --------------------------------------------------------------------------

def _rot_x(a: float) -> list[Vec3]:
    c, s = math.cos(a), math.sin(a)
    return [(1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c)]


def _rot_z(a: float) -> list[Vec3]:
    c, s = math.cos(a), math.sin(a)
    return [(c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0)]


def _matmul(a: list[Vec3], b: list[Vec3]) -> list[Vec3]:
    return [tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3)]


def _col(m: list[Vec3], j: int) -> Vec3:
    return (m[0][j], m[1][j], m[2][j])


@dataclass(frozen=True)
class CameraBasis:
    """Vecteurs unitaires du repere camera, en coordonnees monde.

    right : direction +X ecran (vers la droite de l'image)
    up    : direction +Y ecran (vers le haut de l'image)
    view  : direction de visee (camera -> scene)
    euler : rotation_euler a poser sur l'objet camera dans Blender (ordre XYZ)
    """

    right: Vec3
    up: Vec3
    view: Vec3
    euler: Vec3

    @classmethod
    def from_angles(cls, elevation_deg: float = 30.0, azimuth_deg: float = 45.0) -> "CameraBasis":
        rx = math.radians(90.0 - elevation_deg)
        rz = math.radians(azimuth_deg)
        # Blender applique R = Rz @ Ry @ Rx aux axes locaux (ordre XYZ).
        m = _matmul(_rot_z(rz), _rot_x(rx))
        right, up, back = _col(m, 0), _col(m, 1), _col(m, 2)
        view = (-back[0], -back[1], -back[2])
        return cls(right=right, up=up, view=view, euler=(rx, 0.0, rz))


def project(point: Vec3, target: Vec3, basis: CameraBasis) -> tuple[float, float]:
    """Projette un point monde en coordonnees ecran (metres) relatives a `target`."""
    d = (point[0] - target[0], point[1] - target[1], point[2] - target[2])
    su = sum(d[i] * basis.right[i] for i in range(3))
    sv = sum(d[i] * basis.up[i] for i in range(3))
    return su, sv


def unproject_to_ground(su: float, sv: float, target: Vec3, basis: CameraBasis,
                        ground_z: float = 0.0) -> Vec3:
    """Retro-projette un point ecran sur le plan horizontal z = ground_z."""
    base = tuple(target[i] + su * basis.right[i] + sv * basis.up[i] for i in range(3))
    vz = basis.view[2]
    if abs(vz) < 1e-9:  # camera horizontale : pas d'intersection utilisable
        raise ValueError("La visee est horizontale, aucune intersection avec le sol.")
    t = (ground_z - base[2]) / vz
    return tuple(base[i] + t * basis.view[i] for i in range(3))


# --------------------------------------------------------------------------
# Grille de tuiles
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Tile:
    row: int
    col: int
    name: str
    shift_x: float          # cam.shift_x, en largeurs de cadre
    shift_y: float          # cam.shift_y, en largeurs de cadre
    screen_center: tuple[float, float]      # centre de la tuile en metres ecran
    ground_corners: list[Vec3] = field(default_factory=list)  # TL, TR, BR, BL sur z=0
    ground_center_latlon: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class TileGrid:
    rows: int
    cols: int
    tile_m: float           # largeur d'une tuile a l'ecran, en metres
    tile_px: int
    center_lat: float
    center_lon: float
    origin_lat: float       # scene["lat"] de Blosm
    origin_lon: float       # scene["lon"] de Blosm
    center_xy: tuple[float, float]
    basis: CameraBasis
    ground_z: float = 0.0

    @classmethod
    def build(cls, rows: int, cols: int, tile_m: float, tile_px: int,
              center_lat: float, center_lon: float, origin_lat: float, origin_lon: float,
              elevation_deg: float = 30.0, azimuth_deg: float = 45.0,
              ground_z: float = 0.0) -> "TileGrid":
        cx, cy = latlon_to_xy(center_lat, center_lon, origin_lat, origin_lon)
        return cls(
            rows=rows, cols=cols, tile_m=float(tile_m), tile_px=int(tile_px),
            center_lat=center_lat, center_lon=center_lon,
            origin_lat=origin_lat, origin_lon=origin_lon,
            center_xy=(cx, cy),
            basis=CameraBasis.from_angles(elevation_deg, azimuth_deg),
            ground_z=ground_z,
        )

    @property
    def target(self) -> Vec3:
        """Point du sol vise par l'axe de la camera (centre du mosaique)."""
        return (self.center_xy[0], self.center_xy[1], self.ground_z)

    @property
    def mosaic_px(self) -> tuple[int, int]:
        return (self.cols * self.tile_px, self.rows * self.tile_px)

    def tile_name(self, row: int, col: int) -> str:
        return f"tile_{row}_{col}"

    def tile(self, row: int, col: int) -> Tile:
        shift_x = col - (self.cols - 1) / 2.0
        shift_y = (self.rows - 1) / 2.0 - row
        su = shift_x * self.tile_m
        sv = shift_y * self.tile_m
        h = self.tile_m / 2.0
        # Coins ecran dans l'ordre haut-gauche, haut-droit, bas-droit, bas-gauche.
        corners = [(su - h, sv + h), (su + h, sv + h), (su + h, sv - h), (su - h, sv - h)]
        ground = [unproject_to_ground(u, v, self.target, self.basis, self.ground_z)
                  for u, v in corners]
        gc = unproject_to_ground(su, sv, self.target, self.basis, self.ground_z)
        return Tile(
            row=row, col=col, name=self.tile_name(row, col),
            shift_x=shift_x, shift_y=shift_y, screen_center=(su, sv),
            ground_corners=ground,
            ground_center_latlon=xy_to_latlon(gc[0], gc[1], self.origin_lat, self.origin_lon),
        )

    def tiles(self) -> list[Tile]:
        """Tuiles dans l'ordre de lecture : gauche -> droite, haut -> bas."""
        return [self.tile(r, c) for r in range(self.rows) for c in range(self.cols)]

    def neighbours(self, row: int, col: int) -> dict[str, str | None]:
        """Voisines gauche et haut (celles deja stylisees dans l'ordre de lecture)."""
        return {
            "left": self.tile_name(row, col - 1) if col > 0 else None,
            "top": self.tile_name(row - 1, col) if row > 0 else None,
        }

    def to_index(self) -> dict:
        """Contenu de tiles/index.json."""
        return {
            "schema": 1,
            "grid": {"rows": self.rows, "cols": self.cols},
            "tile": {"metres": self.tile_m, "pixels": self.tile_px},
            "mosaic": {"width_px": self.mosaic_px[0], "height_px": self.mosaic_px[1],
                       "width_m": self.cols * self.tile_m, "height_m": self.rows * self.tile_m},
            "center": {"lat": self.center_lat, "lon": self.center_lon,
                       "blender_x": self.center_xy[0], "blender_y": self.center_xy[1]},
            "scene_origin": {"lat": self.origin_lat, "lon": self.origin_lon},
            "camera": {
                "projection": "ORTHO",
                "elevation_deg": round(math.degrees(math.asin(-self.basis.view[2])), 6),
                "ortho_scale": self.tile_m,
                "euler_xyz_rad": list(self.basis.euler),
                "right": list(self.basis.right),
                "up": list(self.basis.up),
                "view": list(self.basis.view),
            },
            "render_order": [t.name for t in self.tiles()],
            "tiles": [
                {
                    "name": t.name, "row": t.row, "col": t.col,
                    "line": f"{t.name}.png", "semantic": f"{t.name}_sem.png",
                    "shift_x": t.shift_x, "shift_y": t.shift_y,
                    "screen_center_m": list(t.screen_center),
                    "ground_corners_xy": [[p[0], p[1]] for p in t.ground_corners],
                    "ground_center_latlon": list(t.ground_center_latlon),
                    "neighbours": self.neighbours(t.row, t.col),
                }
                for t in self.tiles()
            ],
        }
