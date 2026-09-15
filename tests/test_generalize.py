"""Tests du squelette (ni Blender ni reseau)."""
import sys
from pathlib import Path

from shapely.geometry import LineString, Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import generalize as G  # noqa: E402


def carre(x0, y0, cote):
    return Polygon([(x0, y0), (x0 + cote, y0), (x0 + cote, y0 + cote), (x0, y0 + cote)])


def test_deux_mitoyens_font_un_seul_ilot():
    """Deux maisons qui se touchent sont un ilot, pas deux : c'est la rue qui
    delimite, pas le cadastre."""
    a, b = carre(0, 0, 20), carre(20, 0, 20)
    blocs = G.ilots([a, b], Polygon())
    assert len(blocs) == 1


def test_une_rue_separe_deux_ilots():
    """Sans la soustraction des chaussees, la soudure enjambe la ruelle et colle
    les deux cotes d'une rue."""
    # 2,5 m d'ecart : la dilatation de GLUE (1,5 m de chaque cote) les soude
    a, b = carre(0, 0, 20), carre(22.5, 0, 20)
    rue = LineString([(21.25, -10), (21.25, 40)])
    assert len(G.ilots([a, b], Polygon())) == 1  # sans rue : soude
    corridor = G.corridors([(rue, {"highway": "residential"})])
    assert len(G.ilots([a, b], corridor)) == 2   # avec rue : separes


def test_le_retrait_elargit_la_rue_du_double():
    """SHRINK est retire de CHAQUE cote : la rue gagne deux fois le reglage."""
    avant = G.REGLAGES["SHRINK"]
    try:
        G.REGLAGES["SHRINK"] = 0.0
        large = G.ilots([carre(0, 0, 40)], Polygon())[0]
        G.REGLAGES["SHRINK"] = 3.0
        etroit = G.ilots([carre(0, 0, 40)], Polygon())[0]
    finally:
        G.REGLAGES["SHRINK"] = avant
    x0, _, x1, _ = large.bounds
    a0, _, a1, _ = etroit.bounds
    assert abs((x1 - x0) - (a1 - a0) - 6.0) < 0.3


def test_une_voie_trop_etroite_ne_coupe_pas_un_ilot():
    """Un ilot MicroMacro est borde par des RUES, pas par des passages. En
    laissant les sentiers decouper la masse, le vieux Castres sortait a
    196 ilots pour une cible de 60 a 150 volumes — et l'on ne fait jamais moins
    de volumes que d'ilots, aucun reglage d'aire ne rattrape cela."""
    sentier = [(LineString([(23, -10), (23, 40)]), {"highway": "footway"})]
    assert G.corridors(sentier, min_largeur=5.0).is_empty
    assert not G.corridors(sentier, min_largeur=0.0).is_empty


def test_la_coupe_donne_des_parts_d_aires_egales():
    """A pas egal, un ilot en L donne un volume minuscule et un volume enorme."""
    ell = Polygon([(0, 0), (60, 0), (60, 10), (20, 10), (20, 40), (0, 40)])
    parts = G.couper_en_parts(ell, 3)
    aires = sorted(p.area for p in parts)
    assert abs(sum(aires) - ell.area) < 1.0
    assert aires[-1] / aires[0] < 1.6


def test_un_repere_se_reconnait_sans_etre_nomme():
    assert G.est_repere({"amenity": "place_of_worship"}, [])
    assert G.est_repere({"historic": "yes"}, [])
    assert G.est_repere({"name": "Hôtel de Ville"}, ["hotel de ville"])
    assert not G.est_repere({"building": "yes", "name": "Chez Paul"}, ["goya"])


def test_le_tirage_est_reproductible():
    """Deux executions doivent donner la meme carte, sinon comparer deux rendus
    ne veut plus rien dire."""
    assert G.alea("toit", 3, 1) == G.alea("toit", 3, 1)
    assert G.alea("toit", 3, 1) != G.alea("toit", 3, 2)
