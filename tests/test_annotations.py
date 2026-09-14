"""Tests des annotations a la main."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import annotations as an  # noqa: E402
from geo import TileGrid, project  # noqa: E402

GRID = TileGrid.build(4, 7, 60, 2048, 43.60482, 2.24177, 43.60525, 2.2410, elevation_deg=45)


def test_cell_centres_span_the_tile():
    assert an.cell_centre("A1") == (0.0625, 0.0625)
    assert an.cell_centre("H8") == (0.9375, 0.9375)
    assert an.cell_centre("a1") == an.cell_centre("A1")     # casse indifferente


def test_invalid_cells_are_refused():
    for bad in ("", "A", "I3", "A0", "A9", "42", "AA"):
        with pytest.raises(an.AnnotationError):
            an.cell_centre(bad)


def test_a_cell_lands_inside_its_own_tile():
    """Une case designee doit retomber dans la tuile, pas chez la voisine."""
    tile = next(t for t in GRID.tiles() if t.name == "tile_1_4")
    for cell in ("A1", "D4", "H8", "A8", "H1"):
        x, y = an.to_world("tile_1_4", cell, GRID)
        su, sv = project((x, y, 0.0), GRID.target, GRID.basis)
        assert abs(su - tile.screen_center[0]) < GRID.tile_m / 2
        assert abs(sv - tile.screen_center[1]) < GRID.tile_m / 2


def test_grid_orientation_matches_the_overlay():
    """A gauche, H a droite ; 1 en haut, 8 en bas — comme l'image de reperage."""
    a1 = an.to_world("tile_1_4", "A1", GRID)
    h1 = an.to_world("tile_1_4", "H1", GRID)
    a8 = an.to_world("tile_1_4", "A8", GRID)
    su_a1, sv_a1 = project((*a1, 0.0), GRID.target, GRID.basis)
    su_h1, sv_h1 = project((*h1, 0.0), GRID.target, GRID.basis)
    su_a8, sv_a8 = project((*a8, 0.0), GRID.target, GRID.basis)
    assert su_h1 > su_a1          # H est a droite de A
    assert sv_a8 < sv_a1          # 8 est plus bas que 1


def test_two_cells_average_into_the_middle():
    left = an.to_world("tile_1_4", "B4", GRID)
    right = an.to_world("tile_1_4", "F4", GRID)
    both = an.to_world("tile_1_4", ["B4", "F4"], GRID)
    assert both == pytest.approx(((left[0] + right[0]) / 2, (left[1] + right[1]) / 2))


def test_unknown_kind_is_refused(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"tile_1_4": [{"kind": "licorne", "at": "C4"}]}))
    with pytest.raises(an.AnnotationError, match="type inconnu"):
        an.load(path, GRID)


def test_annotations_carry_a_survey_confidence(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps({
        "_note": "les cles commencant par _ sont ignorees",
        "tile_1_4": [{"kind": "fountain", "at": "C4", "note": "vue sur satellite"}]}))
    loaded = an.load(path, GRID)
    assert len(loaded) == 1 and loaded[0].kind == "fountain"
    assert loaded[0].height == 0.80 and loaded[0].shape == "basin"
    described = an.describe(loaded, GRID)
    assert described[0]["confidence"] == 0.6
    assert described[0]["source"] == "annotation"
    lat, lon = described[0]["latlon"]
    assert 43.60 < lat < 43.61 and 2.23 < lon < 2.25


def test_size_and_height_can_be_overridden(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"tile_1_4": [
        {"kind": "terrace", "at": "F6", "size": [12, 6], "height": 0.3}]}))
    a = an.load(path, GRID)[0]
    assert a.size == (12.0, 6.0) and a.height == 0.3


def test_missing_file_is_not_an_error(tmp_path):
    assert an.load(tmp_path / "absent.json", GRID) == []
