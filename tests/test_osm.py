"""Tests de la partie pure Python de l'importateur OSM (aucun bpy requis)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import osm_to_blend as o  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "mini_ville.osm"


def test_category_rules():
    assert o.category_of({"building": "yes"}) == "building"
    assert o.category_of({"building:part": "yes"}) == "building"
    assert o.category_of({"highway": "residential"}) == "street"
    assert o.category_of({"highway": "pedestrian", "area": "yes"}) is None   # place = sol blanc
    assert o.category_of({"amenity": "parking"}) == "street_area"
    assert o.category_of({"leisure": "park"}) == "vegetation"
    assert o.category_of({"natural": "water"}) == "water"
    assert o.category_of({"waterway": "riverbank"}) == "water"
    assert o.category_of({"name": "Agout"}) is None


def test_building_height_from_tags():
    assert o.building_height({"height": "14"}) == 14.0
    assert o.building_height({"height": "12 m"}) == 12.0
    assert o.building_height({"building:levels": "3"}) == 3 * o.LEVEL_HEIGHT
    assert o.building_height({"building": "yes"}) == o.DEFAULT_LEVELS * o.LEVEL_HEIGHT
    assert o.building_height({"building": "shed", "building:levels": "4"}) == o.LEVEL_HEIGHT


def test_ring_assembly_joins_open_ways_in_any_direction():
    # quatre cotes d'un carre, donnes dans le desordre et parfois inverses
    a, b, c, d = [1, 2], [3, 2], [3, 4], [1, 4]
    rings = o.assemble_rings([a, c, b, d])
    assert len(rings) == 1
    ring = rings[0]
    assert ring[0] == ring[-1]
    assert sorted(set(ring)) == [1, 2, 3, 4]


def test_ring_assembly_ignores_unclosed_fragments():
    assert o.assemble_rings([[1, 2], [2, 3]]) == []


def test_ring_assembly_keeps_already_closed_ways():
    assert o.assemble_rings([[5, 6, 7, 5]]) == [[5, 6, 7, 5]]


def test_ring_area_sign_gives_orientation():
    ccw = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert o.ring_area(ccw) > 0
    assert o.ring_area(ccw[::-1]) < 0


def test_fixture_parses_with_bounds_and_relation():
    osm = o.Osm.parse(FIXTURE)
    assert osm.bounds == (43.603, 2.238, 43.6074, 2.243)
    lat, lon = osm.origin()
    assert abs(lat - 43.6052) < 1e-9 and abs(lon - 2.2405) < 1e-9
    assert len(osm.relations) == 1
    tags, members = osm.relations[0]
    assert tags["building"] == "yes"
    assert {role for role, _ in members} == {"outer", "inner"}
    assert sum(1 for t in osm.node_tags.values() if t.get("natural") == "tree") == 4
