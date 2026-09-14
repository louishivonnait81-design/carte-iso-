"""Tests de la geometrie de grille (aucune dependance a Blender)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from geo import (M_PER_DEG_LAT, CameraBasis, TileGrid, latlon_to_xy, project,
                 unproject_to_ground, xy_to_latlon)

ORIGIN = (43.6010, 2.2335)   # coin sud-ouest de la zone importee dans Blender
CENTER = (43.6052, 2.2405)   # centre de la grille demande


def test_projection_roundtrip():
    x, y = latlon_to_xy(*CENTER, *ORIGIN)
    lat, lon = xy_to_latlon(x, y, *ORIGIN)
    assert abs(lat - CENTER[0]) < 1e-9
    assert abs(lon - CENTER[1]) < 1e-9


def test_projection_scale():
    # 0.0085 deg de latitude (l'etendue nord-sud de la zone) ~ 940 m
    _, y = latlon_to_xy(43.6095, 2.2335, *ORIGIN)
    assert abs(y - 0.0085 * M_PER_DEG_LAT) < 1e-6
    assert 930 < y < 950


def test_camera_basis_is_orthonormal():
    b = CameraBasis.from_angles(30.0, 45.0)
    for v in (b.right, b.up, b.view):
        assert abs(math.sqrt(sum(c * c for c in v)) - 1.0) < 1e-12
    for u, v in ((b.right, b.up), (b.right, b.view), (b.up, b.view)):
        assert abs(sum(a * c for a, c in zip(u, v))) < 1e-12


def test_camera_elevation_is_30_degrees():
    b = CameraBasis.from_angles(30.0, 45.0)
    # la composante verticale de la visee vaut -sin(elevation)
    assert abs(b.view[2] + math.sin(math.radians(30.0))) < 1e-12
    assert b.right[2] == 0.0  # l'horizontale ecran reste horizontale dans le monde


def test_tile_shifts_are_centred_and_contiguous():
    g = TileGrid.build(4, 6, 180, 2048, *CENTER, *ORIGIN)
    tiles = {(t.row, t.col): t for t in g.tiles()}
    assert len(tiles) == 24
    assert sum(t.shift_x for t in tiles.values()) == 0.0
    assert sum(t.shift_y for t in tiles.values()) == 0.0
    # tuiles jointives : un pas de shift = exactement une largeur de tuile
    assert tiles[(0, 1)].screen_center[0] - tiles[(0, 0)].screen_center[0] == 180.0
    assert tiles[(0, 0)].screen_center[1] - tiles[(1, 0)].screen_center[1] == 180.0


def test_render_order_is_reading_order():
    g = TileGrid.build(2, 3, 180, 2048, *CENTER, *ORIGIN)
    assert [t.name for t in g.tiles()] == [
        "tile_0_0", "tile_0_1", "tile_0_2", "tile_1_0", "tile_1_1", "tile_1_2"]


def test_neighbours():
    g = TileGrid.build(2, 3, 180, 2048, *CENTER, *ORIGIN)
    assert g.neighbours(0, 0) == {"left": None, "top": None}
    assert g.neighbours(1, 2) == {"left": "tile_1_1", "top": "tile_0_2"}


def test_ground_corners_are_shared_between_neighbours():
    """Le coin haut-droit d'une tuile est le coin haut-gauche de sa voisine droite."""
    g = TileGrid.build(2, 2, 180, 2048, *CENTER, *ORIGIN)
    a, b = g.tile(0, 0), g.tile(0, 1)
    for pa, pb in zip((a.ground_corners[1], a.ground_corners[2]),
                      (b.ground_corners[0], b.ground_corners[3])):
        assert max(abs(x - y) for x, y in zip(pa, pb)) < 1e-6


def test_screen_projection_is_inverse_of_unprojection():
    g = TileGrid.build(4, 6, 180, 2048, *CENTER, *ORIGIN)
    for su, sv in ((0.0, 0.0), (123.0, -456.0), (-540.0, 360.0)):
        p = unproject_to_ground(su, sv, g.target, g.basis)
        assert abs(p[2]) < 1e-9
        u, v = project(p, g.target, g.basis)
        assert abs(u - su) < 1e-6 and abs(v - sv) < 1e-6


def test_mosaic_size_matches_spec():
    g = TileGrid.build(4, 6, 180, 2048, *CENTER, *ORIGIN)
    assert g.mosaic_px == (12288, 8192)
    idx = g.to_index()
    assert idx["mosaic"]["width_m"] == 1080 and idx["mosaic"]["height_m"] == 720
    assert len(idx["tiles"]) == 24
    assert idx["camera"]["ortho_scale"] == 180
    assert abs(idx["camera"]["elevation_deg"] - 30.0) < 1e-6


def test_semantic_colours_match_what_blender_writes():
    """Blender travaille en lineaire et ecrit du sRGB. Ces valeurs ont ete
    relevees sur des tuiles rendues : elles verrouillent la conversion."""
    from geo import SEMANTIC_SRGB, linear_to_srgb8
    assert SEMANTIC_SRGB["water"] == (170, 206, 243)
    assert SEMANTIC_SRGB["building"] == (225, 225, 225)
    assert SEMANTIC_SRGB["street"] == (144, 144, 144)
    assert SEMANTIC_SRGB["vegetation"] == (149, 211, 149)
    assert SEMANTIC_SRGB["ground"] == (255, 255, 255)
    assert linear_to_srgb8(0.0) == 0 and linear_to_srgb8(1.0) == 255
