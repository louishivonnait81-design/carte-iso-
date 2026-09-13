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
    assert "Image 3 is the same view with flat colors" in job.prompt
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
    assert "Image 4 is the same view with flat colors" in job.prompt
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
