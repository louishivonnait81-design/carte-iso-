"""Tests des mesures de QA sur des images synthetiques."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import qa  # noqa: E402

SIZE = 512


def blocks(offset: int = 0, detail: bool = False) -> np.ndarray:
    """Quelques batiments dessines au trait, eventuellement decales."""
    img = np.full((SIZE, SIZE), 255, np.uint8)
    for x, y, w, h in ((60, 80, 120, 90), (240, 60, 140, 130), (100, 260, 200, 110)):
        x, y = x + offset, y + offset
        img[y:y + h, x:x + 3] = 0
        img[y:y + h, x + w:x + w + 3] = 0
        img[y:y + 3, x:x + w] = 0
        img[y + h:y + h + 3, x:x + w] = 0
        if detail:                       # fenetres ajoutees par le styliseur
            for i in range(3):
                for j in range(2):
                    px, py = x + 20 + i * 30, y + 20 + j * 35
                    img[py:py + 14, px:px + 12] = 0
    return img


def test_identical_tiles_score_high():
    d = qa.drift_score(blocks(), blocks(), tolerance_px=4)
    assert d.recall > 0.95
    assert d.score > 0.9


def test_added_detail_keeps_recall_high():
    """Le styliseur ajoute des fenetres : le squelette reste retrouve (rappel
    eleve), la precision baisse mecaniquement — c'est attendu, pas une derive."""
    d = qa.drift_score(blocks(), blocks(detail=True), tolerance_px=4)
    assert d.recall > 0.95
    assert d.precision < d.recall
    assert d.score > 0.8


def test_dense_noise_scores_near_zero_despite_high_recall():
    """Le point du score ramene au hasard : un dessin tres dense couvre le
    squelette par accident. Le rappel brut reste eleve, le score doit s'effondrer."""
    noise = np.where(np.random.RandomState(0).rand(SIZE, SIZE) < 0.25, 0, 255).astype(np.uint8)
    d = qa.drift_score(blocks(), noise, tolerance_px=4)
    assert d.recall > 0.9          # le hasard couvre presque tout
    assert d.chance > 0.9
    assert d.score < 0.2           # mais il n'y a aucune geometrie commune


def test_shifted_geometry_is_detected():
    good = qa.drift_score(blocks(), blocks(), tolerance_px=4)
    drifted = qa.drift_score(blocks(), blocks(offset=40), tolerance_px=4)
    assert drifted.score < 0.35
    assert drifted.score < good.score


def test_tolerance_absorbs_small_offsets():
    tight = qa.drift_score(blocks(), blocks(offset=6), tolerance_px=1)
    loose = qa.drift_score(blocks(), blocks(offset=6), tolerance_px=8)
    assert loose.recall > tight.recall


def test_seam_perfect_when_lines_continue():
    """Deux moities d'une meme image : la couture doit etre parfaite."""
    whole = np.full((SIZE, 2 * SIZE), 255, np.uint8)
    whole[100:104, :] = 0            # une rue qui traverse les deux tuiles
    whole[300:304, :] = 0
    s = qa.seam_score(whole[:, :SIZE], whole[:, SIZE:], "vertical", band=64)
    assert s.edge_match == 1.0
    assert s.score > 0.95


def test_seam_detects_misaligned_streets():
    left = np.full((SIZE, SIZE), 255, np.uint8)
    right = np.full((SIZE, SIZE), 255, np.uint8)
    left[100:104, :] = 0
    right[220:224, :] = 0            # la rue repart 120 px plus bas
    s = qa.seam_score(left, right, "vertical", band=64)
    assert s.edge_match == 0.0
    assert s.score < 0.4


def test_seam_horizontal_axis_uses_bottom_and_top_edges():
    whole = np.full((2 * SIZE, SIZE), 255, np.uint8)
    whole[:, 150:154] = 0            # une rue verticale traversant la couture
    top, bottom = whole[:SIZE], whole[SIZE:]
    assert qa.seam_score(top, bottom, "horizontal", band=64).edge_match == 1.0


def test_seam_penalises_density_jump():
    plain = np.full((SIZE, SIZE), 255, np.uint8)
    plain[100:104, :] = 0
    busy = plain.copy()
    busy[:, :64] = np.where(np.random.RandomState(0).rand(SIZE, 64) < 0.5, 0, 255)
    busy[100:104, :] = 0
    assert qa.seam_score(plain, busy, "vertical", band=64).score < \
           qa.seam_score(plain, plain, "vertical", band=64).score
