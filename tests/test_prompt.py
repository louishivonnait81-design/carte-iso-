"""Tests d'assemblage du prompt d'habillage (aucun appel reseau)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import stylize  # noqa: E402
from geo import TileGrid  # noqa: E402

SECTIONS = stylize.load_sections(ROOT / "prompts" / "stylize_v2.md")
LIEUX = ROOT / "prompts" / "lieux.md"


def _fake_tiles(tmp_path: Path, rows: int, cols: int) -> tuple[Path, dict]:
    grid = TileGrid.build(rows, cols, 180, 2048, 43.6052, 2.2405, 43.6010, 2.2335)
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()
    index = grid.to_index()
    for tile in index["tiles"]:
        (tiles_dir / tile["line"]).write_bytes(b"line")
        (tiles_dir / tile["semantic"]).write_bytes(b"sem")
    (tiles_dir / "index.json").write_text(json.dumps(index))
    return tiles_dir, index


def test_sections_present():
    assert {"base", "water", "ref02", "left", "top"} <= SECTIONS.keys()


def test_first_tile_has_three_images_and_correct_numbering(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    job = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                            SECTIONS, use_ref02=False, water_mode="off")
    assert job.roles == ["ref01", "lines", "sem"]
    assert job.prompt.startswith("Image 1 is the style reference.")
    assert "Image 2 is a line drawing" in job.prompt
    assert "Image 3 is a COLOUR-CODED KEY" in job.prompt
    assert "Redraw image 2 in exactly the LINE STYLE of image 1" in job.prompt
    assert "EVERY light gray shape in image 3" in job.prompt
    assert "image 4" not in job.prompt and "Image 4" not in job.prompt


def test_second_tile_receives_left_neighbour_as_image_4(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    out = tmp_path / "out"
    out.mkdir()
    (out / "tile_0_0.png").write_bytes(b"styled")     # voisine gauche deja stylisee
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")

    job = stylize.build_job(index["tiles"][1], tiles_dir, out, SECTIONS,
                            use_ref02=False, water_mode="off")
    assert job.roles == ["ref01", "lines", "sem", "left"]
    assert job.images[3].name == "tile_0_0.png"
    assert "Image 4 is the finished tile directly to the LEFT" in job.prompt
    assert "match image 4's right edge exactly" in job.prompt


def test_ref02_shifts_the_numbering(tmp_path, monkeypatch):
    """REF_02 devient l'image 2 : tout le reste doit se renumeroter."""
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    monkeypatch.setattr(stylize, "REF02", tmp_path / "ref02.png")
    stylize.REF01.write_bytes(b"ref1")
    stylize.REF02.write_bytes(b"ref2")

    job = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                            SECTIONS, use_ref02=True, water_mode="off")
    assert job.roles == ["ref01", "ref02", "lines", "sem"]
    assert "Image 3 is a line drawing" in job.prompt
    assert "Image 4 is a COLOUR-CODED KEY" in job.prompt
    assert "Image 2 is a second reference showing the ARCHITECTURE" in job.prompt


def test_top_neighbour_on_second_row(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 2, 2)
    out = tmp_path / "out"
    out.mkdir()
    for name in ("tile_0_0", "tile_0_1", "tile_1_0"):
        (out / f"{name}.png").write_bytes(b"styled")
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")

    tile = next(t for t in index["tiles"] if t["name"] == "tile_1_1")
    job = stylize.build_job(tile, tiles_dir, out, SECTIONS, use_ref02=False, water_mode="off")
    assert job.roles == ["ref01", "lines", "sem", "left", "top"]
    assert "Image 4 is the finished tile directly to the LEFT" in job.prompt
    assert "Image 5 is the finished tile directly ABOVE" in job.prompt
    assert "match image 5's bottom edge exactly" in job.prompt


def test_water_section_added_on_demand(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    off = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                            SECTIONS, use_ref02=False, water_mode="off")
    on = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                           SECTIONS, use_ref02=False, water_mode="on")
    assert "blue marks water" not in off.prompt
    assert "In image 3, blue marks water" in on.prompt


def test_no_placeholder_survives(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 2, 2)
    out = tmp_path / "out"
    out.mkdir()
    (out / "tile_0_1.png").write_bytes(b"styled")
    (out / "tile_1_0.png").write_bytes(b"styled")
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    monkeypatch.setattr(stylize, "REF02", tmp_path / "ref02.png")
    stylize.REF01.write_bytes(b"ref1")
    stylize.REF02.write_bytes(b"ref2")
    tile = next(t for t in index["tiles"] if t["name"] == "tile_1_1")
    job = stylize.build_job(tile, tiles_dir, out, SECTIONS, use_ref02=True, water_mode="on")
    assert "{" not in job.prompt


def test_missing_skeleton_is_a_clear_error(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    (tiles_dir / "tile_0_0_sem.png").unlink()
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    with pytest.raises(SystemExit, match="squelette manquante"):
        stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                          SECTIONS, use_ref02=False, water_mode="off")


def test_cache_key_changes_with_inputs(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    job = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                            SECTIONS, use_ref02=False, water_mode="off")
    before = job.cache_key("m", "1:1", "2K")
    assert before == job.cache_key("m", "1:1", "2K")
    assert before != job.cache_key("m", "1:1", "4K")
    (tiles_dir / "tile_0_0.png").write_bytes(b"line modifiee")
    assert before != job.cache_key("m", "1:1", "2K")


def test_section_set_is_exactly_the_expected_one():
    """Le commentaire d'en-tete du gabarit ne doit pas etre pris pour une section."""
    assert sorted(SECTIONS) == ["anchor", "architecture", "architecture_rules",
                                "base", "geometry_last", "left", "notes", "ref02",
                                "top", "types_dry", "types_wet", "water"]


def test_architecture_section_is_always_included(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    job = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                            SECTIONS, use_ref02=False, water_mode="off")
    assert "There is no third type" in job.prompt   # tuile seche : deux types
    assert "NO PEOPLE, NO ANIMALS" in job.prompt
    assert "NO INVENTED LANDMARKS" in job.prompt
    assert "NOTHING IN THIS DRAWING IS MODERN" in job.prompt
    # les renvois de la section architecture doivent etre resolus eux aussi
    assert "the river and its bridges only where image 3 shows blue" in job.prompt
    assert "Gothic cathedral" not in job.prompt


def test_notes_section_names_real_places(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    notes = {"tile_0_0": [
        {"name": "Cathédrale Saint-Benoît", "kind": "church", "position": "centre",
         "description": "BAROQUE, built 1678-1718"},
        {"name": "Rue Vieille Halle", "kind": "street", "position": "bottom-left"}]}
    with_notes = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                                   SECTIONS, use_ref02=False, water_mode="off", notes=notes)
    without = stylize.build_job(index["tiles"][1], tiles_dir, tmp_path / "out",
                                SECTIONS, use_ref02=False, water_mode="off", notes=notes)
    assert "WHAT IS REALLY HERE" in with_notes.prompt
    assert "- Cathédrale Saint-Benoît (church, centre of this tile): BAROQUE" in with_notes.prompt
    assert "- Rue Vieille Halle (street, bottom-left of this tile)" in with_notes.prompt
    assert "at its position in image 2" in with_notes.prompt
    assert "It never tells you WHERE, HOW BIG or HOW MANY" in with_notes.prompt
    assert "{" not in with_notes.prompt
    assert "WHAT IS REALLY HERE" not in without.prompt   # tuile sans lieu nomme


def test_landscape_reference_is_padded_to_square(tmp_path):
    from PIL import Image
    ref = tmp_path / "ref.png"
    Image.new("RGB", (1408, 768), "black").save(ref)
    sq = stylize.squared(ref)
    with Image.open(sq) as img:
        assert img.size == (1408, 1408)
        px = img.load()
        assert px[0, 0] == (255, 255, 255)        # marge blanche en haut
        assert px[704, 704] == (0, 0, 0)          # contenu centre
    assert stylize.squared(sq) == sq              # deja carre : inchange


def test_ref01_can_be_dropped_and_ref02_carries_the_style(tmp_path, monkeypatch):
    """Sans REF_01, c'est REF_02 qui devient la reference de trait : elle passe
    en image 1 et la section qui la presentait comme un second avis disparait."""
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    monkeypatch.setattr(stylize, "REF02", tmp_path / "ref02.png")
    stylize.REF01.write_bytes(b"ref1")
    stylize.REF02.write_bytes(b"ref2")

    job = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out", SECTIONS,
                            use_ref02=True, water_mode="off", use_ref01=False)
    assert job.roles == ["ref02", "lines", "sem"]
    assert job.prompt.startswith("Image 1 is the style reference.")
    assert "Image 2 is a line drawing" in job.prompt
    assert "second reference showing the ARCHITECTURE" not in job.prompt
    assert "{" not in job.prompt


def test_validated_tile_becomes_the_style_reference(tmp_path, monkeypatch):
    """Une tuile deja validee est une meilleure reference que les planches : vraie
    Castres, bonne echelle, bonne projection. Elle remplace REF_01 et REF_02."""
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    monkeypatch.setattr(stylize, "REF02", tmp_path / "ref02.png")
    stylize.REF01.write_bytes(b"ref1")
    stylize.REF02.write_bytes(b"ref2")
    anchor = tmp_path / "anchor.png"
    anchor.write_bytes(b"tuile validee")

    job = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out", SECTIONS,
                            use_ref02=True, water_mode="off", anchor=anchor)
    assert job.roles == ["anchor", "lines", "sem"]
    assert job.images[0] == anchor
    assert job.prompt.startswith("Image 1 is the style reference.")
    assert "Image 1 is a FINISHED TILE OF THIS SAME MAP" in job.prompt
    assert "your buildings and streets" not in job.prompt   # phrase exacte du gabarit
    assert "yours come from image 2" in job.prompt
    assert "second reference showing the ARCHITECTURE" not in job.prompt
    assert "{" not in job.prompt


def test_anchor_missing_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit, match="ancrage introuvable"):
        stylize.resolve_anchor("tile_9_9", tmp_path)


def test_anchor_that_is_also_the_left_neighbour_is_sent_once(tmp_path, monkeypatch):
    """L'ancre est souvent la voisine de gauche : une seule image, deux roles."""
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    out = tmp_path / "out"
    out.mkdir()
    (out / "tile_0_0.png").write_bytes(b"tuile validee")
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")

    job = stylize.build_job(index["tiles"][1], tiles_dir, out, SECTIONS,
                            use_ref02=False, water_mode="off",
                            anchor=out / "tile_0_0.png")
    assert job.roles == ["anchor", "lines", "sem", "left"]
    assert len(job.images) == 3                      # l'ancre n'est pas envoyee deux fois
    assert job.numbers == [1, 2, 3, 1]               # ancre et voisine gauche = image 1
    assert "Image 1 is a FINISHED TILE OF THIS SAME MAP" in job.prompt
    assert "Image 1 is the finished tile directly to the LEFT" in job.prompt
    assert "image 4" not in job.prompt


def test_geometry_reminder_is_always_last(tmp_path, monkeypatch):
    """La recence a joue contre nous deux fois : une description riche, puis une
    tuile voisine, ont pousse le modele a composer sa propre scene. Le rappel
    geometrique ferme donc le prompt, apres tout le reste."""
    tiles_dir, index = _fake_tiles(tmp_path, 2, 2)
    out = tmp_path / "out"
    out.mkdir()
    (out / "tile_0_1.png").write_bytes(b"styled")
    (out / "tile_1_0.png").write_bytes(b"styled")
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    tile = next(t for t in index["tiles"] if t["name"] == "tile_1_1")
    job = stylize.build_job(tile, tiles_dir, out, SECTIONS, use_ref02=False,
                            water_mode="off")
    assert job.prompt.rstrip().endswith("it is wrong and must be redone.")
    assert "LAST AND ABOVE EVERYTHING ELSE" in job.prompt


def test_no_neighbours_isolates_the_continuity_variable(tmp_path, monkeypatch):
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    out = tmp_path / "out"
    out.mkdir()
    (out / "tile_0_0.png").write_bytes(b"styled")
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    job = stylize.build_job(index["tiles"][1], tiles_dir, out, SECTIONS, use_ref02=False,
                            water_mode="off", no_neighbours=True)
    assert job.roles == ["ref01", "lines", "sem"]
    assert "directly to the LEFT" not in job.prompt


def test_place_jean_jaures_fiche_states_identity_not_composition():
    """Mesure a l'appui, deux fois : une fiche qui decrit la place comme une SCENE
    ("une longue esplanade pavee, les batiments autour d'elle") fait composer au
    modele sa propre place fermee, et la derive tombe a 0,000 — le niveau du
    hasard. La fiche doit donner l'identite (l'arcade continue au rez-de-chaussee)
    et renvoyer explicitement au squelette pour tout ce qui est forme, nombre et
    position."""
    fiche = next(l for l in LIEUX.read_text(encoding="utf-8").splitlines()
                 if l.startswith("- **Place Jean Jaurès**"))
    assert "ARCADE" in fiche
    assert "read from image 3, never invented" in fiche
    for scene in ("long paved esplanade", "The buildings around it"):
        assert scene not in fiche


def test_ink_rule_forbids_grey_not_only_colour():
    """Le premier rendu sans couleur est revenu a 25 %% de gris : chaussee, pans de
    toit et pavage remplis. Interdire la couleur ne suffit pas, il faut nommer le
    gris."""
    ink = SECTIONS["geometry_last"]
    assert "NO GREY" in ink
    assert "TWO TONES AND NO OTHER" in ink


def test_framing_rule_anchors_the_ink_to_the_four_edges():
    """Le rendu flottait au milieu de la page, 16 %% de bande blanche en haut et en
    bas, et fermait la place que le squelette laisse ouverte."""
    base = SECTIONS["base"]
    assert "all four edges of the frame" in base
    assert "do not close what {lines} leaves" in base


def test_dry_tile_is_offered_no_half_timbered_house_on_the_river(tmp_path, monkeypatch):
    """tile_1_4 n'a pas une goutte d'eau, et le modele y a dessine l'Agout, un quai
    et un pont de pierre. Une des causes est la liste fermee des types, qui lui
    offrait la maison a colombage "sur la riviere" meme sur une tuile seche."""
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    dry = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                            SECTIONS, use_ref02=False, water_mode="off")
    assert "THERE IS NO WATER ANYWHERE IN THIS TILE" in dry.prompt
    assert "half-timbered house on the river" not in dry.prompt
    assert "no bridge" in dry.prompt

    wet = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                            SECTIONS, use_ref02=False, water_mode="on")
    assert "half-timbered house on the river" in wet.prompt
    assert "THERE IS NO WATER ANYWHERE IN THIS TILE" not in wet.prompt


def test_has_water_does_not_mistake_pale_green_for_pale_blue(tmp_path):
    """Le redimensionnement interpolait : un bord de disque de vegetation contre du
    blanc produisait un vert pale (207, 235, 207) absent du PNG, a une distance de
    37 du bleu de l'eau — sous l'ancienne tolerance de 40. tile_1_4, sans une
    goutte d'eau, recevait donc la legende de l'Agout, et le modele a dessine une
    riviere et un pont."""
    from PIL import Image
    import numpy as np
    from geo import SEMANTIC_SRGB

    arr = np.full((512, 512, 3), 255, dtype=np.uint8)
    arr[100:200, 100:200] = SEMANTIC_SRGB["vegetation"][:3]
    sec = tmp_path / "vegetation_seule.png"
    Image.fromarray(arr).save(sec)
    assert stylize.has_water(sec) is False

    arr[300:400, 300:400] = SEMANTIC_SRGB["water"][:3]
    wet = tmp_path / "avec_eau.png"
    Image.fromarray(arr).save(wet)
    assert stylize.has_water(wet) is True


def test_notes_off_isolates_the_places_variable(tmp_path, monkeypatch):
    """Le bloc des lieux a grossi jusqu'a 18 entrees decrites. Il faut pouvoir le
    retirer sans rien changer d'autre pour savoir ce qu'il coute en derive."""
    tiles_dir, index = _fake_tiles(tmp_path, 1, 2)
    monkeypatch.setattr(stylize, "REF01", tmp_path / "ref01.png")
    stylize.REF01.write_bytes(b"ref")
    notes = {"tile_0_0": [{"name": "Cathédrale Saint-Benoît", "kind": "church",
                           "position": "centre"}]}
    with_notes = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                                   SECTIONS, use_ref02=False, water_mode="off",
                                   notes=notes)
    without = stylize.build_job(index["tiles"][0], tiles_dir, tmp_path / "out",
                                SECTIONS, use_ref02=False, water_mode="off",
                                notes=notes, notes_mode="off")
    assert "WHAT IS REALLY HERE" in with_notes.prompt
    assert "WHAT IS REALLY HERE" not in without.prompt
    assert without.images == with_notes.images
