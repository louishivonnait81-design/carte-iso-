# MicroMacro-Castres — squelette de la carte

Deux scripts, deux étapes : `generalize.py`, un outil en ligne de commande
testable sans Blender, puis `build_blender.py`, Blender sans fenêtre.

```bash
pip3 install shapely numpy
python3 generalize.py assets/castres.osm blocks.geojson \
  --bbox 43.603,2.235,43.610,2.246 \
  --landmarks "Saint-Benoît,Évêché,Hôtel de Ville,Goya"

/Applications/Blender.app/Contents/MacOS/Blender -b -P build_blender.py -- \
  blocks.geojson out/ 4000
```

Le bbox est `minlat,minlon,maxlat,maxlon`. Le dernier nombre est la largeur du
rendu (4000 pour tester, ~13000 pour 110 cm à 300 dpi). Sorties dans `out/` :
`castres.png`, `castres.svg`, `castres.blend`.

Réglages dans le `dict P` en tête de `generalize.py` ; `ISO_TURN`, `ISO_TILT` et
`LINE_THICKNESS` en tête de `build_blender.py`.

**Boucle de travail** : lancer les deux commandes, regarder `castres.png`,
changer **un seul** paramètre, recommencer. `tasks/00X.md` = une amélioration à
demander sur ces scripts.

Les monuments sont des boîtes à remplacer ; détails et personnages viennent
après, dans Inkscape, sur le SVG.

## Ce que la première exécution a mesuré

Sur `assets/castres.osm`, périmètre 887 × 774 m, rendu à 5000 px :

```
2159 bâtiments, 530 tronçons, 2 eau, 8 parcs, 37 arbres
2147 bâtiments ordinaires → 239 îlots → 405 volumes, 12 monuments
```

Trois écarts, chacun chiffré, chacun avec sa tâche :

| | mesuré | visé | tâche |
|---|---|---|---|
| volumes | **417** | 60 – 150 | `tasks/001` |
| toits plats | **353 / 405 = 87 %** | un centre ancien n'est pas en terrasses | `tasks/002` |
| élévation de la caméra | **35,26°** (`ISO_TILT` 54,7356) | **41°**, mesuré sur la planche | `tasks/003` |

Le SVG passe par l'extension **Freestyle SVG Exporter**, livrée avec
l'application Blender mais absente du module pip `bpy` : elle s'active toute
seule sur un vrai Blender, et le rendu ici se contente du PNG.

## Deux cartes, pas deux qualités

Le squelette ne remplace pas `v2/` tant qu'un choix n'est pas fait ; les deux
vivent côte à côte. Ils ne dessinent pas la même carte. À 110 cm de large :

| | zone couverte | mm par mètre | un personnage de 1,7 m |
|---|---|---|---|
| squelette | 1150 m | 0,96 | **1,6 mm** |
| `v2/` | 311 m | 3,54 | 6,0 mm |

C'est le squelette qui est à l'échelle de la référence : sur la planche
MicroMacro les personnages sont des figures de l'ordre du millimètre.
