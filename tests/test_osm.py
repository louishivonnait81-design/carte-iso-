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
    assert o.category_of({"amenity": "parking"}) == "street_area"
    assert o.category_of({"leisure": "park"}) == "vegetation"
    assert o.category_of({"natural": "water"}) == "water"
    assert o.category_of({"waterway": "riverbank"}) == "water"
    assert o.category_of({"name": "Agout"}) is None


def test_car_free_ways_are_open_ground_not_street():
    """Une esplanade pietonne classee 'rue' ressortait en gris fonce, et le
    modele y dessinait chaussee, passages pietons et voitures : c'est ce qui est
    arrive a la place Jean Jaures."""
    for tags in ({"highway": "pedestrian"}, {"highway": "footway"},
                 {"highway": "path"}, {"highway": "steps"},
                 {"highway": "pedestrian", "area": "yes"}, {"place": "square"}):
        assert o.category_of(tags) == "open_ground", tags
    # les voies ouvertes aux voitures restent des rues
    for tags in ({"highway": "residential"}, {"highway": "primary"},
                 {"highway": "living_street"}, {"highway": "service"}):
        assert o.category_of(tags) == "street", tags


def test_building_height_from_tags():
    assert o.building_height({"height": "14"})[0] == 14.0
    assert o.building_height({"height": "12 m"})[0] == 12.0
    assert o.building_height({"building:levels": "3"})[0] == 3 * o.LEVEL_HEIGHT
    assert o.building_height({"building": "yes"})[0] == o.DEFAULT_LEVELS * o.LEVEL_HEIGHT
    assert o.building_height({"building": "shed", "building:levels": "4"})[0] == o.LEVEL_HEIGHT


def test_height_provenance_is_recorded():
    """Sur Castres, 3 738 batiments sur 3 763 n'ont aucune hauteur : une valeur
    devinee ne doit pas etre indiscernable d'une valeur mesuree."""
    assert o.building_height({"height": "14"})[1:] == ("measured", 0.98)
    assert o.building_height({"building:levels": "3"})[1:] == ("levels", 0.90)
    assert o.building_height({"building": "church"})[1:] == ("kind", 0.55)
    assert o.building_height({"building": "yes"})[1:] == ("default", 0.35)


def test_measured_heights_take_precedence():
    """Le point d'entree pour du LiDAR HD, de la BD TOPO ou une correction
    manuelle : une hauteur relevee prime sur le tag OSM lui-meme."""
    tags = {"height": "9", "building:levels": "2"}
    assert o.building_height(tags, measured={42: 17.8}, osm_id=42) == (17.8, "measured", 0.98)
    assert o.building_height(tags, measured={42: 17.8}, osm_id=7)[0] == 9.0


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
