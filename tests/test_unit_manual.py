"""Tests de la preparation d'une unite (ni Blender ni reseau)."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import unit_manual as um  # noqa: E402


def test_a_non_square_unit_is_padded_and_cropped_back_exactly():
    """Les modeles d'image recopient le rapport de forme de leur entree. Une
    unite de 1423x1673 revenait avec quelques pour cent d'ecart, et la remettre a
    l'echelle de sa boite l'aurait deformee. On l'envoie donc centree sur un
    carre, et on redecoupe la fenetre d'origine au retour."""
    original = Image.new("L", (1423, 1673), 255)
    original.putpixel((0, 0), 0)
    original.putpixel((1422, 1672), 0)

    square, (ox, oy, side) = um.squared(original)
    assert square.size == (1673, 1673)
    assert (ox, oy) == (125, 0)

    back = square.crop((ox, oy, ox + 1423, oy + 1673))
    assert back.size == original.size
    assert back.getpixel((0, 0)) == 0
    assert back.getpixel((1422, 1672)) == 0


def test_padding_is_white_not_black():
    """Le fond part au modele : s'il etait noir, il lui demanderait de l'encre."""
    square, (ox, _, _) = um.squared(Image.new("L", (10, 40), 255))
    assert square.getpixel((0, 0)) == 255
    assert ox == 15


def test_a_fiche_is_attached_only_when_the_row_carries_that_name():
    fiches = {"place jean jaurès": "ARCADE partout.",
              "cathédrale saint-benoît": "Baroque, pas gothique."}
    names = {11: "Place Jean Jaurès", 22: "Boulangerie Dupont"}

    with_fiche = um.note_for({"way_ids": [11, 22]}, fiches, names)
    assert "ARCADE partout." in with_fiche
    assert "Baroque" not in with_fiche
    assert "wins over the general rules" in with_fiche

    assert um.note_for({"way_ids": [22]}, fiches, names) == ""
    assert um.note_for({"way_ids": [99]}, fiches, names) == ""


def test_the_same_fiche_is_not_repeated_for_a_row_of_several_buildings():
    fiches = {"jean jaurès": "ARCADE partout."}
    names = {1: "Place Jean Jaurès", 2: "Place Jean Jaurès", 3: "Place Jean Jaurès"}
    note = um.note_for({"way_ids": [1, 2, 3]}, fiches, names)
    assert note.count("ARCADE partout.") == 1


def test_import_refuses_a_drawing_the_model_has_cropped(tmp_path, monkeypatch):
    """Une sortie non carree veut dire que le modele a recadre. Le collage se
    ferait alors sur une fenetre fausse, et le decalage serait invisible a
    l'oeil : mieux vaut refuser."""
    monkeypatch.setattr(um, "OUT", tmp_path / "manual_units")
    monkeypatch.setattr(um, "DRAWN", tmp_path / "drawn")
    folder = um.OUT / "u1"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps(
        {"unit": "u1", "pad": [10, 0], "square": 100, "size": [80, 100],
         "box": [0, 0]}), encoding="utf-8")

    bad = tmp_path / "bad.png"
    Image.new("L", (100, 60), 255).save(bad)
    with pytest.raises(SystemExit):
        um.import_drawing("u1", bad, allow_nonsquare=False)

    good = tmp_path / "good.png"
    Image.new("L", (100, 100), 255).save(good)
    out = um.import_drawing("u1", good, allow_nonsquare=False)
    assert Image.open(out).size == (80, 100)


def test_prompt_never_speaks_of_position_or_of_the_rest_of_the_map():
    """Tout l'interet du decoupage en unites est la : le placement n'est plus une
    affaire de prompt. Si ces mots reviennent, c'est qu'on redonne au modele une
    responsabilite qu'on lui a retiree."""
    text = um.TEMPLATE.read_text(encoding="utf-8")
    body = text[text.index("-->") + 3:]
    for forbidden in ("of this tile", "in this tile", "neighbouring tile",
                      "corner to corner", "COLOUR-CODED KEY", "bottom-right",
                      "small piece of a large map"):
        assert forbidden not in body, forbidden
    # "tile" ne doit subsister que comme tuile de TOIT
    import re
    for m in re.finditer(r"\btiles?\b", body):
        around = body[max(0, m.start() - 40):m.end() + 20].lower()
        assert "terracotta" in around or "roof" in around or "courses" in around, around
    assert "THE SILHOUETTE IS FIXED" in body
    assert "KEEP THE FRAME" in body


def test_silhouette_iou_is_the_metric_that_matters_now():
    """Ce que l'on mesure a change avec l'architecture. En mode tuile on mesurait
    une DERIVE DE POSITION, parce que le modele placait la matiere. Il ne la
    place plus : le compositeur pose le dessin a la boite. Ce qui reste a
    mesurer est donc la SILHOUETTE — un dessin qui deborde du masque est rogne,
    un dessin qui le remplit mal laisse des trous.

    Premiere mesure reelle sur u83180702, 9 batiments, place Jean Jaures :
        ChatGPT  IoU 0,888   couverture du masque 0,957
        Gemini   IoU 0,808   couverture du masque 0,970
    a comparer aux 0,461 de derive du meilleur rendu par tuile.
    """
    import numpy as np
    ref = np.zeros((40, 40), bool)
    ref[10:30, 10:30] = True

    exact = ref.copy()
    assert _iou(exact, ref) == 1.0

    shifted = np.zeros_like(ref)
    shifted[12:32, 12:32] = True
    assert 0.6 < _iou(shifted, ref) < 0.8

    half = np.zeros_like(ref)
    half[10:30, 10:20] = True
    assert _iou(half, ref) == pytest.approx(0.5)


def _iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))
