"""Tests des regles de rendu qui ne demandent pas de scene Blender."""
import os
import sys
from pathlib import Path

os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import iso_tiles as it  # noqa: E402


class FakeObject:
    """Un objet Blender vu par is_tree : un nom et des proprietes."""

    def __init__(self, name, **props):
        self.name = name
        self._props = props
        self.hide_render = False

    def get(self, key, default=None):
        return self._props.get(key, default)


def test_trees_are_recognised_by_tag_or_by_name():
    assert it.is_tree(FakeObject("tree.1234"))
    assert it.is_tree(FakeObject("noeud.9", natural="tree"))
    assert not it.is_tree(FakeObject("building.42"))
    assert not it.is_tree(FakeObject("street.7", highway="residential"))
    # un objet dont le nom contient "tree" sans le prefixe n'en est pas un
    assert not it.is_tree(FakeObject("streetlamp.3"))


def test_hiding_trees_only_touches_trees():
    class FakeScene:
        objects = [FakeObject("tree.1"), FakeObject("building.2"),
                   FakeObject("noeud.3", natural="tree"), FakeObject("street.4")]

    scene = FakeScene()
    assert it.show_trees(scene, False) == 2
    assert [o.hide_render for o in scene.objects] == [True, False, True, False]
    assert it.show_trees(scene, True) == 2
    assert not any(o.hide_render for o in scene.objects)


def test_detail_lines_are_thinner_than_masses():
    """La hierarchie n'a de sens que si l'ecart est net."""
    assert 0.3 <= it.DETAIL_RATIO <= 0.6


def test_semantic_colours_come_from_the_shared_table():
    from geo import SEMANTIC_LINEAR
    assert it.SEMANTIC_COLORS is SEMANTIC_LINEAR
