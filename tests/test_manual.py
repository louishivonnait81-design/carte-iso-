"""Tests du mode manuel (export / import), sans reseau."""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from geo import TileGrid  # noqa: E402


def _setup(tmp_path: Path) -> dict[str, Path]:
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    grid = TileGrid.build(1, 2, 180, 64, 43.6052, 2.2405, 43.6010, 2.2335)
    index = grid.to_index()
    index["tile"]["pixels"] = 64
    (tiles / "index.json").write_text(json.dumps(index))
    for tile in index["tiles"]:
        Image.new("L", (64, 64), 255).save(tiles / tile["line"])
        Image.new("RGB", (64, 64), "white").save(tiles / tile["semantic"])
    return {"tiles": tiles, "styled": tmp_path / "styled", "manual": tmp_path / "manual"}


def _run(paths: dict[str, Path], *args: str, ref01: Path | None = None) -> str:
    # --ref02 off : le test ne doit pas dependre de la presence de assets/REF_02
    cmd = [sys.executable, str(ROOT / "manual.py"),
           "--tiles", str(paths["tiles"]), "--styled", str(paths["styled"]),
           "--out", str(paths["manual"]), "--ref02", "off", *args]
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT)}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_export_then_import_then_next(tmp_path, monkeypatch):
    paths = _setup(tmp_path)
    ref01 = ROOT / "assets" / "REF_01_style.png"
    created = not ref01.exists()
    if created:
        Image.new("L", (64, 64), 255).save(ref01)
    try:
        out = _run(paths, "next")
        assert "tile_0_0" in out and "3 images" in out
        folder = paths["manual"] / "tile_0_0"
        assert sorted(p.name for p in folder.iterdir()) == [
            "1_ref01.png", "2_lines.png", "3_sem.png", "LISEZMOI.txt", "job.json",
            "prompt.txt"]
        prompt = (folder / "prompt.txt").read_text(encoding="utf-8")
        assert prompt.startswith("Image 1 is the style reference.")
        assert "image 4" not in prompt

        # on simule le telechargement depuis Gemini
        downloaded = tmp_path / "gemini.png"
        Image.new("RGB", (2048, 2048), "white").save(downloaded)
        _run(paths, "import", "tile_0_0", str(downloaded))
        assert (paths["styled"] / "tile_0_0.png").exists()

        out = _run(paths, "next")
        assert "tile_0_1" in out and "4 images" in out
        prompt = (paths["manual"] / "tile_0_1" / "prompt.txt").read_text(encoding="utf-8")
        assert "Image 4 is the finished tile directly to the LEFT" in prompt
        assert (paths["manual"] / "tile_0_1" / "4_left.png").exists()

        assert "1/2 tuiles stylisees" in _run(paths, "status")
    finally:
        if created:
            ref01.unlink()


def test_nonsquare_import_is_refused(tmp_path):
    """Une tuile non carree casse la correspondance avec le squelette Blender."""
    paths = _setup(tmp_path)
    wide = tmp_path / "paysage.png"
    Image.new("RGB", (1024, 559), "white").save(wide)

    cmd = [sys.executable, str(ROOT / "manual.py"), "--styled", str(paths["styled"]),
           "import", "tile_0_0", str(wide)]
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT)}
    refused = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert refused.returncode != 0
    assert "NON CARREE" in refused.stderr
    assert not (paths["styled"] / "tile_0_0.png").exists()

    forced = subprocess.run(cmd + ["--allow-nonsquare"], capture_output=True, text=True, env=env)
    assert forced.returncode == 0
    assert (paths["styled"] / "tile_0_0.png").exists()


def test_status_flags_tiles_whose_neighbour_was_redone(tmp_path):
    """Refaire une tuile perime ses voisines droite et basse : elles ont ete
    dessinees d'apres une version qui n'existe plus."""
    paths = _setup(tmp_path)
    ref01 = ROOT / "assets" / "REF_01_style.png"
    created = not ref01.exists()
    if created:
        Image.new("L", (64, 64), 255).save(ref01)
    try:
        square = tmp_path / "rendu.png"
        Image.new("RGB", (512, 512), "white").save(square)

        _run(paths, "next")                                   # exporte tile_0_0
        _run(paths, "import", "tile_0_0", str(square))
        _run(paths, "next")                                   # tile_0_1, voit tile_0_0
        _run(paths, "import", "tile_0_1", str(square))
        assert "perimees" not in _run(paths, "status")

        # on refait tile_0_0 avec une image differente
        autre = tmp_path / "autre.png"
        Image.new("RGB", (512, 512), (250, 250, 250)).save(autre)
        _run(paths, "import", "tile_0_0", str(autre), "--force")

        out = _run(paths, "status")
        assert "1 perimees" in out
        assert "a refaire : tile_0_1" in out
    finally:
        if created:
            ref01.unlink()
