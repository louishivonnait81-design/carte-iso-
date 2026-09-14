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


def test_public_buildings_tagged_building_yes_are_recognised_by_function():
    """L'eglise Saint-Jean-Saint-Louis est taguee building=yes : elle se
    retrouvait a 8 m, la hauteur d'une maison de ville."""
    church = {"building": "yes", "amenity": "place_of_worship", "name": "Église X"}
    height, source, _ = o.building_height(church)
    assert height == 16.0 and source == "kind"
    assert o.building_height({"building": "yes", "tourism": "museum"})[0] == 12.0
    assert o.building_height({"building": "yes", "amenity": "townhall"})[0] == 13.0
    # un tag explicite garde la main
    assert o.building_height({"building": "yes", "amenity": "place_of_worship",
                              "building:levels": "2"})[0] == 2 * o.LEVEL_HEIGHT


def test_height_jitter_is_deterministic_and_unbiased():
    """89,6 % des batiments n'ont aucune donnee de hauteur et recevaient tous la
    meme valeur : 1258 sur 1397 mesuraient exactement 8,00 m, et 95 % des unites
    sortaient en dalle. La variation appliquee est une invention assumee, mais
    elle doit etre deterministe — sinon deux executions donnent deux cartes — et
    ne pas deplacer l'echelle d'ensemble."""
    ids = list(range(83180000, 83181000))
    once = [o.building_height({"building": "yes"}, osm_id=i)[0] for i in ids]
    twice = [o.building_height({"building": "yes"}, osm_id=i)[0] for i in ids]
    assert once == twice

    base = o.DEFAULT_LEVELS * o.LEVEL_HEIGHT
    assert abs(sum(once) / len(once) - base) < 0.15
    assert min(once) >= base - o.HEIGHT_JITTER_M - 1e-9
    assert max(once) <= base + o.HEIGHT_JITTER_M + 1e-9
    # les etages ne varient pas continument
    assert len(set(once)) <= 2 * int(o.HEIGHT_JITTER_M
                                     / o.HEIGHT_JITTER_STEP) + 1
    assert len(set(once)) >= 5      # et la rangee n'est plus plate


def test_only_the_default_branch_is_jittered():
    """Une hauteur relevee, ou deduite des niveaux tagues, ou du type de
    batiment, est une donnee : on n'y touche pas. Le jour ou le LiDAR arrive,
    aucune variation ne s'applique."""
    measured, src, _ = o.building_height({"height": "14"}, osm_id=7)
    assert (measured, src) == (14.0, "measured")

    levels, src, _ = o.building_height({"building": "yes",
                                                   "building:levels": "3"}, osm_id=7)
    assert src == "levels"
    assert levels == 3 * o.LEVEL_HEIGHT

    church, src, _ = o.building_height({"building": "church"}, osm_id=7)
    assert src == "kind"
    assert church == o.HEIGHT_BY_KIND["church"]

    # meme identifiant, meme tags : seule la branche par defaut bouge
    plain, src, _ = o.building_height({"building": "yes"}, osm_id=7)
    assert src == "default"
    assert plain != o.DEFAULT_LEVELS * o.LEVEL_HEIGHT


def test_jitter_can_be_switched_off():
    base = o.DEFAULT_LEVELS * o.LEVEL_HEIGHT
    flat, _, _ = o.building_height({"building": "yes"}, osm_id=7, jitter=0)
    assert flat == base
