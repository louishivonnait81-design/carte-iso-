# MicroMacro-Castres — squelette de la carte

Deux scripts, deux étapes : un outil en ligne de commande testable sans Blender,
puis Blender sans fenêtre.

## 1. Récupérer le .osm

Soit le fichier que Blosm a déjà téléchargé (dossier de cache Blosm, réglé dans
ses préférences), soit un export direct : openstreetmap.org → Exporter → tracer
la zone → `castres.osm`. Le dépôt en contient déjà un : `assets/castres.osm`.

## 2. Généraliser

```bash
pip3 install shapely numpy
python3 generalize.py assets/castres.osm blocks.geojson \
  --bbox 43.603,2.235,43.610,2.246 \
  --landmarks "Saint-Benoît,Évêché,Hôtel de Ville,Goya"
```

Le bbox est `minlat,minlon,maxlat,maxlon`. Les noms de `--landmarks` sont
cherchés dans le tag `name` OSM, accents et casse ignorés ; les églises et les
bâtiments `historic` sont repérés tout seuls et ne sont **jamais** fondus dans
un îlot.

Le script affiche `bâtiments → îlots → volumes` et dit de quel côté corriger.

| Paramètre | Effet | Défaut |
|---|---|---|
| `SHRINK` | recul des volumes = largeur ajoutée aux rues | 2.5 m |
| `ROAD_EXTRA` | mètres ajoutés à toutes les rues | 1.5 |
| `M2_PER_VOLUME` | m² d'îlot par volume (plus grand = moins de volumes) | 450 |
| `MAX_LEVELS` | plafond d'étages | 3 |
| `SIMPLIFY` | tolérance de simplification des contours | 2.5 m |
| `GABLE_PROB` | proportion de petits volumes à toit à 2 pans | 0.6 |
| `RUE_MIN_LARGEUR` | en deçà, une voie ne découpe pas un îlot | 5.0 m |
| `GLUE` | dilatation qui soude les mitoyens en îlot | 1.5 m |
| `MIN_VOLUME_M2` | sous cette aire, un volume n'est pas dessiné | 60 |
| `LEVEL_HEIGHT` / `DEFAULT_LEVELS` | hauteur d'étage, étages par défaut | 3.0 / 2 |
| `GABLE_MAX_M2` | au-delà, un volume prend une croupe | 200 |
| `LEVEL_JITTER` | casse la ligne de toits, en étages | 0.35 |

**`M2_PER_VOLUME` ne suffit pas à atteindre la cible**, et c'est le premier
piège : on ne fait jamais moins de volumes que d'îlots. Avec les réglages par
défaut le vieux Castres sort à 196 îlots, donc au mieux 196 volumes. Ce qui
commande vraiment le compte, ce sont `RUE_MIN_LARGEUR` (laisser les sentiers
découper la masse la pulvérise), `GLUE` et `MIN_VOLUME_M2`.

Un jeu qui tombe dans la cible sur tout le vieux Castres :

```bash
python3 generalize.py assets/castres.osm blocks.geojson \
  --bbox 43.603,2.235,43.610,2.246 \
  --landmarks "Saint-Benoît,Évêché,Hôtel de Ville,Goya" \
  --set RUE_MIN_LARGEUR=6.5 --set M2_PER_VOLUME=2000 \
  --set MIN_VOLUME_M2=250 --set GLUE=3
# 1952 batiments -> 101 ilots -> 124 volumes (+ 9 reperes, 21 surfaces)
# objectif MicroMacro 60-150 volumes : 133 -> dans la cible
```

## 3. Construire et rendre dans Blender

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b -P build_blender.py -- \
  blocks.geojson out/ 4000
```

Le dernier nombre est la largeur du rendu en pixels (4000 pour tester, ~13000
pour 110 cm à 300 dpi). Sorties dans `out/` : `castres.png`, `castres.svg`
(Inkscape) et `castres.blend`.

Le SVG passe par l'extension **Freestyle SVG Exporter**, livrée avec
l'application Blender mais **absente du module pip `bpy`** : le script l'active
tout seul sur un vrai Blender, et le dit quand elle manque — le PNG et le
`.blend` sortent quand même.

En tête de `build_blender.py` : `ISO_TURN` (45 / 135 / 225 / 315),
`ISO_ELEVATION`, `LINE_THICKNESS` et `LINE_REF_WIDTH`.

`ISO_ELEVATION` vaut **41** parce que c'est la valeur mesurée sur une planche
MicroMacro, pas une préférence : voir `MESURES.md`. `LINE_THICKNESS` suit la
résolution — Freestyle compte en pixels absolus, et sans cette mise à l'échelle
un aperçu ment sur le trait.

## Boucle de travail

1. lancer les deux commandes ;
2. regarder `castres.png` ;
3. changer **un seul** paramètre ;
4. recommencer.

`tasks/00X.md` = une amélioration à demander sur ces scripts.

## Ce que le squelette ne fait pas (volontairement)

Monuments dessinés (les repères sont des boîtes à remplacer), détails,
personnages : étapes 4 à 6, dans Inkscape, sur le SVG.

## Ce que le squelette n'est pas

Ce n'est pas le pipeline `v2/`, et il ne le remplace pas tant qu'un choix n'a
pas été fait — les deux vivent côte à côte dans le dépôt. Ils ne dessinent pas
la même carte : le squelette couvre **tout le vieux Castres en 123 volumes**,
`v2/` couvre **220 m autour de la place en 265 bâtiments**. Comparés à l'échelle
du papier, à 110 cm de large :

| | zone couverte | mm par mètre | un personnage de 1,7 m |
|---|---|---|---|
| squelette | 1198 m | 0,92 | 1,6 mm |
| `v2/` | 311 m | 3,54 | 6,0 mm |

C'est le squelette qui est à l'échelle de la référence. Le prix se voit aussi :
sur les 220 m du cœur, la généralisation réglée pour la cible ne laisse que
**13 volumes**, et la place Jean-Jaurès disparaît.
