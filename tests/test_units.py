"""Tests du regroupement des batiments en unites de dessin (ni Blender ni reseau)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from units import (Building, adjacency_groups, build_units, split_long_group,  # noqa: E402
                   units_touching, unit_name)


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


def test_units_touching_keeps_a_row_straddling_the_border():
    """Une rangee coupee par la frontiere d'une tuile appartient aux deux. Elle
    est dessinee une fois et collee une fois : le compositeur travaille sur la
    carte entiere, pas tuile par tuile."""
    bs = {1: _box(1, -5, 0, w=20), 2: _box(2, 100, 100)}
    units = build_units(bs)
    touching = units_touching(units, (0, 0, 60, 60))
    assert [u.name for u in touching] == ["u1"]
