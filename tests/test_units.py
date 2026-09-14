"""Tests du regroupement des batiments en unites de dessin (ni Blender ni reseau)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from units import (Building, adjacency_groups, boxes_touching, build_units,  # noqa: E402
                   split_long_group, unit_name)


def _box(wid: int, x0: float, y0: float, w: float = 10.0, d: float = 10.0,
         nodes=None) -> Building:
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + d), (x0, y0 + d)]
    return Building(way_id=wid, points=pts, tags={"building": "yes"},
                    nodes=nodes if nodes is not None else [wid * 10 + i for i in range(4)])


def test_buildings_sharing_a_node_form_one_row():
    """Deux facades mitoyennes ont ete saisies avec le meme point : c'est la
    trace, dans les donnees, du mur partage."""
    a = _box(1, 0, 0, nodes=[100, 101, 102, 103])
    b = _box(2, 10, 0, nodes=[102, 103, 104, 105])   # partage 102 et 103
    c = _box(3, 40, 0, nodes=[200, 201, 202, 203])   # isole
    groups = adjacency_groups({1: a, 2: b, 3: c})
    assert sorted(len(g) for g in groups) == [1, 2]
    joined = next(g for g in groups if len(g) == 2)
    assert joined == [1, 2]


def test_group_order_is_stable():
    """Deux executions doivent produire les memes noms d'unites, sinon les cles
    de cache et les dessins deja valides ne se retrouvent plus."""
    bs = {1: _box(1, 0, 0, nodes=[1, 2, 3, 4]),
          2: _box(2, 10, 0, nodes=[3, 4, 5, 6]),
          3: _box(3, 40, 0, nodes=[7, 8, 9, 10])}
    first = [u.name for u in build_units(bs)]
    shuffled = {k: bs[k] for k in reversed(list(bs))}
    assert [u.name for u in build_units(shuffled)] == first


def test_a_row_longer_than_the_limit_is_sliced_along_its_axis():
    """La plus grande rangee mitoyenne de Castres compte 81 batiments et
    traverse plusieurs tuiles : d'un bloc, elle ne ferait que quelques pixels
    par metre."""
    bs = {}
    shared = 500
    for i in range(10):                       # 10 x 10 m = 100 m de long
        bs[i + 1] = _box(i + 1, i * 10, 0, nodes=[shared + i, shared + i + 1])
    parts = split_long_group(sorted(bs), bs, max_extent=45.0)
    assert len(parts) > 1
    assert sum(len(p) for p in parts) == 10          # aucun batiment perdu
    assert sorted(w for p in parts for w in p) == sorted(bs)   # ni duplique
    for p in parts:
        pts = [pt for w in p for pt in bs[w].points]
        assert max(pt[0] for pt in pts) - min(pt[0] for pt in pts) <= 45.0
    # les tranches restent des morceaux continus de la rangee
    for p in parts:
        assert p == sorted(p)


def test_a_lone_building_is_never_sliced():
    bs = {1: _box(1, 0, 0, w=90, d=90)}
    assert split_long_group([1], bs, max_extent=45.0) == [[1]]


def test_unit_name_survives_reordering():
    assert unit_name([7, 3, 11]) == unit_name([11, 7, 3]) == "u3"


def test_selection_is_done_on_screen_boxes_not_on_ground_boxes():
    """L'emprise au sol d'une tuile isometrique est un LOSANGE. Selectionner les
    unites avec le rectangle aligne sur ses quatre coins debordait de deux
    tuiles : le controle de chainage est tombe a 5 % de concordance au lieu de
    95. La selection se fait donc sur la boite EN PIXELS, celle-la meme qui
    servira au collage — les deux ne peuvent plus se contredire."""
    boxes = {"dedans": (8300, 2500, 400, 400),
             "a_cheval": (8100, 2000, 300, 300),
             "dehors": (100, 100, 200, 200),
             "juste_a_cote": (8192 + 2048, 2048, 100, 100)}
    keep = boxes_touching(boxes, (8192, 2048, 2048, 2048))
    assert keep == {"dedans", "a_cheval"}


def test_a_box_touching_only_by_its_edge_is_excluded():
    """Deux boites qui se touchent bord a bord ne se recouvrent pas : sans cela
    chaque unite appartiendrait a ses quatre voisines."""
    assert boxes_touching({"u": (0, 0, 10, 10)}, (10, 0, 10, 10)) == set()
    assert boxes_touching({"u": (0, 0, 11, 10)}, (10, 0, 10, 10)) == {"u"}


def test_compose_places_each_unit_at_its_own_box():
    """Le compositeur pose a la boite, pas a l'image : un dessin revenu a une
    autre taille est remis a l'echelle de sa boite, jamais l'inverse."""
    import json
    import sys
    from PIL import Image
    sys.path.insert(0, str(ROOT))
    import compose as C

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        units = Path(d)
        # deux unites de 20x20, l'une posee sur l'autre a un endroit connu
        for name, val in (("a", 0), ("b", 0)):
            Image.new("L", (20, 20), val).save(units / f"{name}_line.png")
            Image.new("L", (20, 20), 255).save(units / f"{name}_mask.png")
        index = {"grid": {"mosaic_px": [100, 100], "tile_px": 50},
                 "units": [
                     {"name": "a", "order": 0, "x": 5, "y": 5, "w": 20, "h": 20,
                      "line": "a_line.png", "mask": "a_mask.png"},
                     {"name": "b", "order": 1, "x": 60, "y": 60, "w": 20, "h": 20,
                      "line": "b_line.png", "mask": "b_mask.png"}]}
        (units / "index.json").write_text(json.dumps(index), encoding="utf-8")
        canvas = C.compose(index, units, None)

    assert canvas.size == (100, 100)
    assert canvas.getpixel((10, 10)) == 0     # unite a, posee en (5,5)
    assert canvas.getpixel((65, 65)) == 0     # unite b, posee en (60,60)
    assert canvas.getpixel((40, 40)) == 255   # rien entre les deux


def test_compose_rescales_a_drawing_that_came_back_the_wrong_size():
    """Le modele rend rarement la taille exacte demandee. C'est la boite qui fait
    foi : le dessin est remis a son echelle, il ne deplace jamais la boite."""
    import json
    import sys
    import tempfile
    from PIL import Image
    sys.path.insert(0, str(ROOT))
    import compose as C

    with tempfile.TemporaryDirectory() as d:
        units, drawn = Path(d) / "u", Path(d) / "dessins"
        units.mkdir()
        drawn.mkdir()
        Image.new("L", (20, 20), 128).save(units / "a_line.png")
        Image.new("L", (20, 20), 255).save(units / "a_mask.png")
        Image.new("L", (77, 77), 0).save(drawn / "a.png")      # mauvaise taille
        index = {"grid": {"mosaic_px": [100, 100], "tile_px": 50},
                 "units": [{"name": "a", "order": 0, "x": 5, "y": 5, "w": 20, "h": 20,
                            "line": "a_line.png", "mask": "a_mask.png"}]}
        canvas = C.compose(index, units, drawn)

    assert canvas.getpixel((10, 10)) == 0      # le dessin, pas le rendu brut
    assert canvas.getpixel((30, 30)) == 255    # et rien hors de la boite


def test_the_chain_check_ignores_the_paste_dilation():
    """Le controle juge le CALCUL DES BOITES, pas la politique de collage. Les
    3 px de dilatation font deliberement deborder chaque unite hors de sa
    silhouette exacte, ce qui abaissait la concordance de 81,5 % a 74,0 % sans
    qu'aucune unite ait bouge. Baisser le seuil pour l'accepter aurait masque de
    vraies erreurs de placement : le controle compose donc sans dilatation."""
    import inspect
    import sys
    sys.path.insert(0, str(ROOT))
    import compose as C
    source = inspect.getsource(C.check)
    assert "grow_px=0" in source
    assert C.MASK_GROW_PX > 0            # mais le collage reel, lui, dilate
