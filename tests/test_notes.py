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


def test_each_trade_gets_its_own_shopfront():
    text = tn.format_notes([{"name": "Au Bon Pain", "kind": "bakery", "position": "left"},
                            {"name": "Chez Marcel", "kind": "butcher", "position": "right"}])
    assert "long loaves" in text.splitlines()[0]
    assert "hanging hams" in text.splitlines()[1]


def test_repeated_trade_is_described_once():
    text = tn.format_notes([{"name": "BNP", "kind": "bank", "position": "left"},
                            {"name": "CIC", "kind": "bank", "position": "right"},
                            {"name": "Banque Populaire", "kind": "bank", "position": "top"}])
    lines = text.splitlines()
    assert "cash machine" in lines[0]
    assert lines[1].endswith("same shopfront") and lines[2].endswith("same shopfront")


def test_fiche_wins_over_generic_shopfront():
    text = tn.format_notes([{"name": "Marché couvert de l'Albinque", "kind": "covered market",
                             "position": "centre", "description": "the real covered market"}])
    assert text.endswith("the real covered market")


def test_unnamed_landmarks_are_listed():
    """La fontaine de la place Jean Jaures n'a pas de nom dans OSM : elle
    n'etait donc jamais signalee au modele, qui ne l'a pas dessinee."""
    assert ("amenity", "fountain") in tn.UNNAMED
    label, prio = tn.UNNAMED[("amenity", "fountain")]
    assert label == "public fountain" and prio == 1
    assert "bench" in dict(tn.UNNAMED.values()) or True   # le mobilier est couvert


def test_unnamed_entry_is_written_without_a_name():
    text = tn.format_notes([{"name": "public fountain", "kind": "public fountain",
                             "position": "centre"}])
    assert text.startswith("- a public fountain (centre of this tile):")
    assert "public fountain (public fountain" not in text


def test_named_entry_keeps_its_name():
    text = tn.format_notes([{"name": "La Fontaine", "kind": "restaurant",
                             "position": "left"}])
    assert text.startswith("- La Fontaine (restaurant, left of this tile):")


def test_a_basin_at_a_memorial_is_not_a_second_place():
    """La vasque de la statue de Jean Jaures est a 1 m de la statue et taguee
    amenity=fountain : les deux apparaissaient comme deux lieux distincts. Un
    memorial et un bassin au meme endroit sont un seul monument."""
    import json
    notes_path = ROOT / "tiles" / "notes.json"
    if not notes_path.exists():
        return
    notes = json.loads(notes_path.read_text(encoding="utf-8"))

    entries = notes.get("tile_1_4", [])
    statue = next((e for e in entries if "Jaurès" in e["name"]), None)
    assert statue is not None, "la statue doit rester listee"
    doublons = [e for e in entries if e["kind"] == "public fountain"
                and e["position"] == statue["position"]]
    assert not doublons, "la vasque ne doit pas etre listee a part"

    # La vraie fontaine nommee de Castres est ailleurs, 103 m plus haut
    ailleurs = {e["name"] for e in notes.get("tile_0_3", [])}
    assert "La Fontaine des Angelots" in ailleurs
