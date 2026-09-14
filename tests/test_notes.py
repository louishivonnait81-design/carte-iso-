"""Tests de l'extracteur de lieux par tuile."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tile_notes as tn  # noqa: E402
from geo import TileGrid  # noqa: E402
from osm_to_blend import Osm  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "mini_ville.osm"


def test_kind_priorities():
    assert tn.kind_of({"place": "square"}) == ("square", 1)
    assert tn.kind_of({"amenity": "cafe"}) == ("café", 4)
    assert tn.kind_of({"shop": "hats"}) == ("shop", 6)          # joker shop=*
    assert tn.kind_of({"highway": "residential"}) == ("street", 3)
    assert tn.kind_of({"highway": "bus_stop"}) is None            # ignore
    assert tn.kind_of({"name": "x"}) is None


def test_position_labels():
    assert tn.position_label(0, 0, 60) == "centre"
    assert tn.position_label(-25, 25, 60) == "top-left"
    assert tn.position_label(25, -25, 60) == "bottom-right"
    assert tn.position_label(0, 25, 60) == "top"
    assert tn.position_label(25, 0, 60) == "right"


def test_fiches_parse_and_match():
    fiches = tn.load_fiches(ROOT / "prompts" / "lieux.md")
    assert fiches, "prompts/lieux.md doit contenir des fiches"
    desc = next(d for pat, d in fiches if pat.search("Cathédrale Saint-Benoît de Castres"))
    assert "BAROQUE" in desc and "NOT Gothic" in desc


def test_street_spanning_tiles_is_noted_in_each(tmp_path):
    osm = Osm.parse(FIXTURE)
    g = TileGrid.build(1, 2, 180, 2048, 43.6052, 2.2405, *osm.origin(), elevation_deg=45)
    notes = tn.build_notes(g.to_index(), osm, [])
    # "Rue Test" court de x=-200 a x=200 : elle traverse les deux tuiles
    tiles_with_street = {t for t, es in notes.items() if any(e["name"] == "Rue Test" for e in es)}
    assert tiles_with_street == {"tile_0_0", "tile_0_1"}


def test_format_notes_lines():
    text = tn.format_notes([{"name": "Place X", "kind": "square", "position": "centre",
                             "description": "a square"},
                            {"name": "Rue Y", "kind": "street", "position": "top"}])
    assert text.splitlines() == ["- Place X (square, centre of this tile): a square",
                                 "- Rue Y (street, top of this tile)"]
