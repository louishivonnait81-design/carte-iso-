"""Tests de la mesure de visibilite des chemins (ni Blender ni reseau)."""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "v2"))

import jouabilite as J  # noqa: E402

PAS = 0.25


def _grille(ny: int, nx: int) -> np.ndarray:
    return np.zeros((ny, nx), dtype=np.float32)


def test_un_mur_avale_une_largeur_proportionnelle_a_sa_hauteur():
    """C'est le chiffre qui commande toute l'etape 5b : vue a 60 degres depuis
    le sud-ouest, une facade de hauteur h cache 0,408 h de sol le long d'un axe.
    Une ruelle de 4 m bordee de 10 m de mur n'a donc plus un seul pixel de sol,
    quelle que soit la resolution du rendu."""
    h = _grille(200, 200)
    h[:, :20] = 10.0                       # un mur de 10 m, puis du vide
    cache = J.ombre(h, PAS, 60.0)
    # sur une ligne loin du bord, les cellules libres cachees a la suite du mur
    portee = int(cache[150, 20:].sum()) * PAS
    attendu = 10.0 * math.cos(math.radians(45.0)) / math.tan(math.radians(60.0))
    assert abs(portee - attendu) < 2 * PAS, (portee, attendu)


def test_l_ombre_recule_quand_la_camera_monte():
    h = _grille(200, 200)
    h[:, :20] = 10.0
    basse = J.ombre(h, PAS, 45.0)[150, 20:].sum()
    haute = J.ombre(h, PAS, 75.0)[150, 20:].sum()
    assert haute < basse / 2


def test_une_traversee_tronquee_par_le_bord_n_est_pas_mesuree():
    """Un segment libre qui touche le bord du tableau n'a pas de largeur : elle
    est coupee par le cadre, pas par du bati. La compter ferait entrer dans la
    mesure des ruelles de largeur inventee."""
    libre = np.zeros((1, 20), dtype=bool)
    libre[0, :5] = True                    # colle au bord gauche
    libre[0, 8:12] = True                  # bornee des deux cotes
    largeurs = [w for w, *_ in J.segments(libre, 1, PAS)]
    assert largeurs == [4 * PAS]


def test_une_courette_fermee_n_est_pas_un_chemin():
    """Un puits de lumiere au milieu d'un ilot est invisible ET inaccessible :
    le compter parmi les ruelles noires gonflait le defaut d'un tiers sans
    qu'aucun personnage puisse jamais y marcher."""
    libre = np.zeros((20, 20), dtype=bool)
    libre[0, :] = True                     # une rue au bord
    libre[9:11, 9:11] = True               # une courette enfermee
    vu = J.accessible(libre)
    assert vu[0, 5]
    assert not vu[9, 9]


def test_le_rapport_voit_la_rue_s_elargir():
    """Controle de bout en bout : deux barres de 10 m de haut separees par une
    ruelle. En l'ecartant, la part jouable doit monter."""
    def part(ecart_cellules: int) -> float:
        h = _grille(120, 120)
        h[:, 20:40] = 10.0
        h[:, 40 + ecart_cellules:60 + ecart_cellules] = 10.0
        return J.rapport(h, PAS, 60.0)["nord_sud"]["part_jouable"]

    assert part(4) == 0.0                  # 1 m de rue : rien a voir
    assert part(60) > 0.9                  # 15 m de rue : tout se joue
