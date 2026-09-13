"""Tests de la mesure de densite : distinguer un trait econome d'une texture."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ink_density  # noqa: E402

BOXES = ((100, 120, 300, 260), (500, 90, 380, 330), (180, 540, 520, 300))


def _plate(textured: bool) -> Image.Image:
    a = np.full((1024, 1024), 255, np.uint8)
    for x, y, w, h in BOXES:
        a[y:y + h, x:x + 3] = 0
        a[y:y + h, x + w:x + w + 3] = 0
        a[y:y + 3, x:x + w] = 0
        a[y + h:y + h + 3, x:x + w] = 0
        if textured:                      # chaque tuile / chaque pierre dessinee
            a[y:y + h:10, x:x + w] = 0
            a[y:y + h, x:x + w:10] = 0
    return Image.fromarray(a)


def _gray_after_reduction(img: Image.Image, scale: float = 0.15) -> float:
    small = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    return ink_density.measure(small)[1]


def test_pure_white_has_no_ink_and_no_gray():
    ink, gray = ink_density.measure(Image.new("L", (256, 256), 255))
    assert ink == 0.0 and gray == 0.0


def test_pure_black_is_all_ink():
    ink, gray = ink_density.measure(Image.new("L", (256, 256), 0))
    assert ink == 1.0 and gray == 0.0


def test_flat_midtone_is_all_gray():
    """Un aplat gris est exactement ce que le cahier des charges interdit."""
    ink, gray = ink_density.measure(Image.new("L", (256, 256), 128))
    assert gray == 1.0 and ink == 0.0


def test_economical_line_art_stays_white_when_reduced():
    assert _gray_after_reduction(_plate(textured=False)) < 0.10


def test_fine_texture_turns_gray_when_reduced():
    assert _gray_after_reduction(_plate(textured=True)) > 0.30


def test_texture_is_clearly_separated_from_clean_line_art():
    clean = _gray_after_reduction(_plate(textured=False))
    dense = _gray_after_reduction(_plate(textured=True))
    assert dense > 4 * clean


def test_full_size_ink_alone_would_not_catch_it():
    """A taille reelle les deux planches paraissent legeres : c'est la reduction
    qui revele le probleme. Cela justifie de mesurer apres reduction."""
    clean = ink_density.measure(_plate(textured=False))[0]
    dense = ink_density.measure(_plate(textured=True))[0]
    assert clean < 0.05 and dense < 0.10
