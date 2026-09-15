# v2 — la carte entièrement en Blender

Onze scripts numérotés, relançables seuls, tous en ligne de commande. Aucune API
externe, aucun générateur d'images : **Blender et Python, rien d'autre.** Tout
paramètre modifiable vit dans `config.json` ; les scripts ne contiennent aucune
valeur en dur.

```
blender -b -P v2/00_check.py        # Blender, Blosm, moteur disponible
blender -b -P v2/01_bbox.py -- --coeur --centre "Place Jean Jaurès" --cote 220
blender -b -P v2/02_import.py       #            -> castres_base.blend
blender -b -P v2/03_camera.py       # cadrage, Freestyle, rendu de contrôle
blender -b -P v2/04_previews.py     # les quatre orientations
blender -b -P v2/05_sol.py          # clippage + dalle -> castres_sol.blend
blender -b -P v2/05b_rues.py        # jouabilité      -> castres_rues.blend
blender -b -P v2/06_toits.py        # croupes et acrotères -> castres_toits.blend
blender -b -P v2/07_facades.py      # baies, portes, arcades -> castres_facades.blend
blender -b -P v2/08_mobilier.py     # arbres, bancs, fontaines
blender -b -P v2/09_cheminees.py    #                 -> castres_final.blend
blender -b -P v2/10_pavage.py       # joints, nappes  -> castres_pave.blend
blender -b -P v2/11_ouvertures.py   # dix toits ouverts -> castres_ouvert.blend
blender -b -P v2/03_camera.py -- --blend v2/castres_ouvert.blend --largeur 8000 \
        --moteur CYCLES --sortie v2/carte_8000.png
```

Dans le conteneur, sans GPU, les aperçus se font avec `--moteur CYCLES` : sur
cette scène plate et émissive il est une vingtaine de fois plus rapide qu'EEVEE
en rendu logiciel. Sur le Mac, le défaut `BLENDER_EEVEE` de `config.json`
s'applique. Freestyle ne fonctionne avec aucun des deux Workbench.

## Les trois inventions, et elles sont les seules

La géométrie vient d'OpenStreetMap. Trois écarts sont assumés, tous bornés, tous
dans `config.json`, tous annulables en remettant `0` :

| paramètre | valeur | ce qu'il corrige |
|---|---|---|
| `soudure_ilot_m` | 2,5 | les fentes de 40 cm entre deux maisons mitoyennes saisies séparément |
| `retrait_ilot_m` | 2,0 | les rues trop étroites pour qu'on y fasse marcher quelqu'un |
| `echelle_hauteur` | 0,7 | l'ombre des murs, qui avale 0,408 h de largeur apparente |
| `toits_ouverts.liste` | 10 lieux | on ne voit pas l'intérieur d'une maison fermée |

La liste des toits ouverts est un choix éditorial, pas une mesure : elle s'édite
à la main dans `config.json`. `11_ouvertures.py --choisir` la refabrique depuis
OSM (poids du commerce × racine de l'emprise, 35 m minimum entre deux) si on
veut repartir d'une base neutre.

Ce que chacun a changé est mesuré dans [`../MESURES.md`](../MESURES.md) et se
revérifie à tout moment :

```
blender -b -P v2/mesure_rues.py -- --blend v2/castres_rues.blend --carte controle.png
```

`v2/jouabilite.py` contient la mesure elle-même, sans Blender, donc testée
(`pytest tests/test_jouabilite.py`).
