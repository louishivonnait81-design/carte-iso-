# MicroMacro Castres

Carte de jeu type *MicroMacro Crime City* du vieux Castres : vue isométrique 30°,
trait noir sur blanc pur, style cartoon ligne claire. **La géométrie vient de
Blender / OpenStreetMap ; l'IA générative ne fait que le style.** Toute dérive de
géométrie est un défaut mesuré par `qa.py`, pas une fatalité.

Les personnages viendront plus tard, sur un calque séparé (`characters.py`, non
commencé).

## État du dépôt

Le pipeline tourne **de bout en bout** dans l'environnement de développement,
validé sur une ville synthétique (`tests/fixtures/mini_ville.osm`) : extrait OSM →
scène Blender → tuiles lignes et sémantiques → mosaïque aux raccords exacts.

**Il manque les vraies données.** Trois fichiers à déposer dans `assets/` :

| Manquant | Où le prendre | Conséquence |
|---|---|---|
| `castres.osm` | téléchargé dans un navigateur, voir ci-dessous | aucune géométrie |
| `REF_01_style.png` | votre image | aucun habillage possible |
| `REF_02_castres.png` | la planche v3 validée | architecture non contrainte |

> `castres.blend` n'existait pas : il est désormais **construit ici** par
> `scripts/osm_to_blend.py` à partir d'un extrait OSM, à la place de l'import
> Blosm. Toutes les sources OSM (openstreetmap.org, Overpass et ses miroirs,
> Geofabrik) sont bloquées par le proxy de l'environnement de rendu, d'où le
> passage par le navigateur :
>
> https://api.openstreetmap.org/api/0.6/map?bbox=2.2335,43.6010,2.2485,43.6095
>
> (repli si « too many nodes » :
> https://overpass-api.de/api/map?bbox=2.2335,43.6010,2.2485,43.6095)

## Zone et échelle

Le cahier des charges initial visait tout le vieux Castres (900 × 610 m) en
tuiles de 180 m. La première tuile passée par Gemini a montré que c'était
injouable : une tuile de 180 m aligne déjà 25 à 30 bâtiments, soit toute une
carte *MicroMacro Crime City* (110 × 75 cm, ~20 bâtiments en largeur, un
personnage ≈ 1 cm). Pour retrouver cette proportion il faut ~33 px/m à 2048 px,
donc des **tuiles de 60 m**, et une carte couvre alors 300 à 400 m de ville.

Cadre retenu, trouvé par recherche systématique (azimut × grille × centre) sur
neuf lieux nommés extraits de l'OSM :

* **7 colonnes × 4 lignes de 60 m, 28 tuiles, 420 × 240 m, 14 336 × 8 192 px**
* centre **43.60482 / 2.24177**, élévation **45°**, azimut 45°
* contient Pont Vieux, Pont Neuf, place Jean Jaurès, place Saint-Jacques, la
  cathédrale Saint-Benoît, l'hôtel de ville et le musée Goya, le jardin de
  l'Évêché, le théâtre et la place de la République ; l'Agout traverse la carte
  en diagonale.
* `qa_out/plan_cadre_7x3.png` montre le cadre sur le plan OSM.

L'extrait OSM importé reste le grand rectangle (lat 43.6010 → 43.6095, lon
2.2335 → 2.2485) : la scène Blender contient toute la vieille ville, seule la
grille rendue est réduite. Changer de cadre ne demande qu'un nouveau
`--center-latlon`.

**Pourquoi 45° et non 30°.** À 30°, un bâtiment de 9,5 m masque 16,5 m de sol
derrière lui : les ruelles de 4 à 6 m du vieux Castres disparaissent. À 45°, il
n'en masque que 9,5 m, la trame des rues se lit et il reste assez de façade pour
les fenêtres. REF_01 elle-même est vue plus près de 45° que de 30°.

## Installation

```bash
make install                    # dépendances Python (3.11)
make test                       # 70 tests, ni Blender ni réseau requis
export GEMINI_API_KEY=...       # mode API seulement — jamais dans le dépôt
```

### Blender

`render.py` cherche Blender dans cet ordre : `$BLENDER_BIN`, `blender` dans le
PATH, `third_party/blender*/blender`, puis le module pip `bpy`.

Dans l'environnement de développement, `download.blender.org` est bloqué mais le
module pip `bpy` (5.0) s'installe depuis PyPI et **rend correctement sans GPU** à
condition d'avoir Mesa en logiciel (paquets listés dans `requirements.txt`,
`LIBGL_ALWAYS_SOFTWARE=1`). Mesuré : Workbench et Cycles CPU rendent une tuile en
moins d'une seconde ; EEVEE en logiciel met vingt fois plus. La passe lignes
tourne donc sur **Cycles** (Freestyle y est supporté, la scène étant un aplat
émissif quelques échantillons suffisent), la passe sémantique sur Workbench.

### De l'extrait OSM à la scène — `scripts/osm_to_blend.py`

```bash
make blend          # assets/castres.osm -> assets/castres.blend
```

* Bâtiments : empreintes extrudées à `height`, sinon `building:levels × 3,2 m`,
  sinon 2,5 niveaux (le vieux Castres est R+1 / R+2). Multipolygones gérés — un
  hôtel particulier garde sa cour. Une **toiture à croupes** est ajoutée par
  rentrée du dessus jusqu'au faîte (pente 28°, celle des tuiles canal) : en trait,
  un bâtiment sans faîte se lit comme une boîte et le modèle dessine des toits
  plats.
* Rues : courbes au sol, largeur par classe OSM dans `obj["road_width"]`
  (résidentielle 6 m, tertiaire 7 m, passage 2,5 m…), ponts surélevés d'un mètre.
* Végétation : surfaces plates + arbres isolés en icosphères.
* Eau : surfaces plates juste au-dessus du sol blanc.
* Origine de scène (`scene["lat"]`, `scene["lon"]`) = centre de l'emprise, comme
  chez Blosm ; les tags OSM sont recopiés en propriétés personnalisées.

## Deux façons d'habiller les tuiles

L'étape de style peut se faire **à la main** (compte Gemini personnel, copier-coller)
ou **par l'API**. Tout le reste du pipeline est identique : dans les deux cas les
tuiles finies atterrissent dans `styled/<tuile>.png`, et `qa.py` / `assemble.py`
n'y voient aucune différence.

### Mode manuel (par défaut aujourd'hui — aucune clé, aucune dépense)

```bash
make render                                   # 1. tuiles Blender -> tiles/
make next                                     # 2. prépare manual/tile_0_0/
#   -> téléverser les images NUMÉROTÉES DANS L'ORDRE, coller prompt.txt
python manual.py import tile_0_0 ~/Downloads/gemini.png
make next                                     # 3. la suivante reçoit sa voisine gauche
make status                                   #    avancement de la grille
make qa && make seam && make assemble
```

`manual.py export` crée un dossier par tuile contenant `prompt.txt`, un
`LISEZMOI.txt` et les images à téléverser renommées `1_ref01.png`,
`2_lines.png`, `3_sem.png`, `4_left.png`, `5_top.png`. **L'ordre est ce qui fait
tenir le prompt** : le texte y renvoie par numéro. `import` **refuse** une image non carrée
(`--allow-nonsquare` pour passer outre) : l'interface web ignore souvent la
consigne « output square » et renvoie du 16:9, or une tuile non carrée ne
correspond plus au squelette Blender — la géométrie dérive et tous les raccords
sautent. En mode API, `--aspect-ratio 1:1` est un vrai paramètre du SDK, pas une
consigne en langue naturelle : c'est le deuxième argument sérieux pour l'API,
après `seed`.

Faire les tuiles **une par une, dans l'ordre de lecture** : chacune a besoin de ses
voisines déjà finies pour la continuité. `manual.py export --all` existe mais
n'apporte alors aucune continuité.

Des prompts déjà rendus, prêts à coller, sont dans `prompts/rendus/`.

### Mode API

```bash
export GEMINI_API_KEY=...
make ref02         # planche d'architecture castraise (à valider à l'œil)
make stylize-dry   # vérifier les prompts sans dépenser un centime
make stylize       # habillage -> styled/ (plafond 5 €)
```

### 1. `render.py` → `scripts/iso_tiles.py`

```bash
blender -b assets/castres.blend -P scripts/iso_tiles.py -- \
    --rows 4 --cols 6 --tile 180 --center-latlon 43.6052 2.2405 --out tiles/
```

* **Projection lat/lon → Blender** : équirectangulaire locale autour de
  l'origine Blosm (`scene["lat"]`, `scene["lon"]`, surchargeable par
  `--origin-latlon`) : `x = (lon − lon0) × 111320 × cos(lat0)`,
  `y = (lat − lat0) × 110540`.
* **Caméra** : orthographique, élévation 30°, azimut 45°
  (`rotation_euler = (60°, 0, 45°)`), `ortho_scale = --tile`. Le tuilage se fait
  par `cam.shift_x` / `cam.shift_y`, d'un pas de 1,0 = une largeur de tuile : les
  tuiles sont jointives par construction, pas par recalage a posteriori.
* **Deux passes** : lignes noires (EEVEE + Freestyle, override matériau blanc
  émissif, monde blanc) et aplats sémantiques (Workbench, éclairage `FLAT`,
  couleur par objet, anticrénelage coupé).
* **Sorties** : `tiles/tile_L_C.png`, `tiles/tile_L_C_sem.png`, `tiles/index.json`
  (grille, tailles, centre, ordre de rendu, voisines, empreinte au sol de chaque
  tuile en lat/lon).
* Reprend là où il s'est arrêté ; `--force` pour re-rendre.

**Classement sémantique.** Les objets sont classés par mots-clés cherchés dans
leur nom, celui de leurs collections et leurs propriétés personnalisées.
`osm_to_blend.py` nomme tout de façon à tomber juste ; pour une scène venue
d'ailleurs, `--dump-categories` affiche le classement et `DEFAULT_RULES` en tête
de `scripts/iso_tiles.py` s'ajuste.

| catégorie | couleur | note |
|---|---|---|
| bâtiment | gris clair | |
| rue / trottoir | gris foncé | **voies ouvertes aux voitures seulement** ; élargies en rubans plats |
| sol piéton | blanc | `pedestrian`, `footway`, `path`, `steps`, `place=square` |
| végétation | vert | |
| **eau** | **bleu** | **ajout** au cahier des charges, voir ci-dessous |
| sol ouvert | blanc | cours, places, plan de sol sous toute la grille |

> **Écart assumé, à valider :** le cahier des charges ne prévoit que quatre
> couleurs. L'Agout traverse la zone : sans couleur propre il tomberait en
> « blanc = sol ouvert » et le modèle y poserait des bâtiments. L'eau a donc sa
> couleur, et une phrase de légende correspondante est ajoutée au prompt
> **uniquement quand du bleu est détecté** dans la tuile `_sem`
> (`stylize.py --water auto|on|off`). Dire si vous préférez revenir à quatre
> couleurs strictes.

### 2. `stylize.py`

Traite les tuiles dans l'ordre de lecture. Pour chacune, envoie dans l'ordre :
**REF_01**, *(REF_02 si présent)*, la tuile lignes, la tuile `_sem`, puis les
voisines **déjà stylisées** — gauche, puis haut.

* Modèle par défaut : `gemini-3-pro-image-preview` (Nano Banana Pro), surchargeable
  par `--model` ou `GEMINI_IMAGE_MODEL`. `python scripts/gemini.py --list-models`
  interroge l'API pour afficher les modèles image réellement disponibles sur la clé
  — **à faire avant le premier vrai run**, la doc officielle Google
  (`ai.google.dev`, `docs.cloud.google.com`) étant bloquée par le proxy ici. Les
  paramètres `image_config.aspect_ratio` / `image_size` sont eux confirmés par
  introspection du SDK officiel `google-genai` 2.23.
* Sortie carrée, `2K` par défaut (`--image-size 1K|2K|4K`).
* `--temperature 0.35` et `--seed 1789` par défaut : c'est le seul vrai levier de
  constance d'une tuile à l'autre, et **il n'existe pas dans l'interface web**.
  C'est l'argument le plus solide pour passer à l'API le jour où la variabilité
  entre tuiles devient gênante.
* Cache disque + reprise : une tuile déjà produite n'est **jamais** écrasée sans
  `--force` ; si ses entrées ont changé depuis, le message le signale.
* Retries avec backoff exponentiel et jitter sur les erreurs transitoires.
* Coût estimé par appel et cumulé, journalisé dans `styled/<tuile>.json` et
  `styled/.budget.json`.
* **Plafond de dépense** : `--budget-eur 5` par défaut ; le script s'arrête avant
  de dépasser et demande de relancer avec un plafond explicite.
* `--dry-run` écrit les prompts dans `styled/prompts/` sans appeler l'API.

**Le prompt** est dans `prompts/stylize_v2.md`, découpé en sections
(`base`, `architecture`, `notes`, `water`, `ref02`, `left`, `top`). Les renvois aux
images y sont des variables (`{lines}`, `{sem}`, `{left}`…) et non des numéros
écrits en dur : quand REF_02 s'ajoute, tout se renumérote automatiquement. C'est le
seul écart au texte fourni, et il est couvert par les tests (`tests/test_prompt.py`).

### Ce qu'il y a vraiment dans la tuile — `scripts/tile_notes.py`

```bash
python scripts/tile_notes.py        # -> tiles/notes.json
```

Le prompt de base dit *comment* dessiner ; il ne dit jamais *ce qu'il y a*. Or le
modèle connaît Castres. Chaque tuile reçoit donc la liste des lieux nommés qui la
touchent, extraits de l'OSM avec leur position dans la tuile :

* les **lieux notables** portent une fiche rédigée dans `prompts/lieux.md`
  (cathédrale, palais épiscopal, jardin de l'Évêché, ponts, maisons sur l'Agout,
  place Jean Jaurès, théâtre, hôtels particuliers). Ces fiches sont écrites de
  mémoire et **restent à vérifier par quelqu'un qui connaît la ville** : une fiche
  fausse vaut pire qu'aucune. Elles ont déjà corrigé une erreur du cahier des
  charges — Saint-Benoît n'est pas gothique mais baroque (1678-1718) ;
* les **commerces** reçoivent la devanture de leur métier (`DEVANTURES` dans
  `tile_notes.py`) : pains en corbeilles chez le boulanger, jambons pendus chez le
  boucher, buckets de fleurs chez le fleuriste, grille et présentoirs de velours
  chez le bijoutier. Une devanture n'est décrite qu'à sa première occurrence dans
  la tuile — trois banques n'ont pas besoin de trois fois la même phrase ;
* les chemins sont échantillonnés le long de leurs segments : une rue droite n'a
  que deux nœuds, tous deux hors de la tuile qu'elle traverse pourtant.

Les noms disent quoi dessiner ; ils ne sont **jamais lettrés** — une enseigne peut
porter un emblème dessiné, jamais un mot.

### Deux garde-fous pour la chaîne de 28 tuiles

**Ancrer le style sur une tuile validée** — `--anchor tile_1_4`

Une fois une tuile approuvée, elle devient la meilleure référence de style
possible : vraie Castres, bonne échelle, bonne projection, bonne épaisseur de
trait. REF_01 et REF_02 sont des planches hors échelle et hors projection ; la
première est même la seule image parisienne du lot. Passée en `--anchor`, la tuile
validée les remplace toutes les deux, devient l'image 1, et le prompt lui demande
de tout reprendre **sauf la géométrie**.

Sans cela, le style dérive en chaîne : la tuile 20 est dessinée d'après des
voisines elles-mêmes dessinées d'après des voisines, à quatre générations de la
référence d'origine.

**Repérer les tuiles périmées** — `make status`

Refaire une tuile change l'image de continuité de ses voisines droite et basse :
elles ont été dessinées d'après une version qui n'existe plus. `manual.py`
enregistre l'empreinte des entrées de chaque tuile à l'export et la recompare à
l'import ; `status` marque `!!` celles qui ont divergé. Sans ce contrôle,
l'incohérence ne se voit qu'à l'assemblage final, quand il est trop tard.

```
   ## ## !! .. .. .. ..
   ## .. .. .. .. .. ..
```

### Provenance et confiance des hauteurs

`make blend` écrit `assets/castres_confidence.json` : pour chaque bâtiment, sa
hauteur, d'où elle vient et à quel point on peut s'y fier.

| source | confiance | Castres |
|---|---|---|
| `measured` — tag `height`, ou relevé fourni | 0,98 | **0 %** |
| `levels` — `building:levels` × 3,2 m | 0,90 | 0,7 % |
| `kind` — déduite du type (église, immeuble, garage) | 0,55 | 4,0 % |
| `default` — 2,5 niveaux, faute de mieux | 0,35 | **95,4 %** |

C'est le maillon le plus faible de la géométrie, et sans ce suivi une hauteur
devinée était indiscernable d'une hauteur mesurée. Le point d'entrée pour la
corriger existe :

```bash
make blend HEIGHTS=heights.json      # {osm_id: hauteur_m}
```

Ce fichier peut venir du **LiDAR HD de l'IGN**, de la BD TOPO, ou de corrections à
la main sur les bâtiments qui comptent. Attention : `data.geopf.fr`, `wxs.ign.fr`,
`geoservices.ign.fr` et `api-adresse.data.gouv.fr` sont **tous bloqués** par le
proxy de l'environnement de rendu — comme l'extrait OSM, ces données doivent être
téléchargées depuis un navigateur.

### Relire les données avant de générer — `scripts/contact_sheet.py`

```bash
make planche        # qa_out/planche_sem.png et planche_lines.png
```

Les 28 tuiles côte à côte avec leur nom. Le goût du modèle n'est pas le goulot
d'étranglement, **la justesse des données l'est** : la place Jean Jaurès est une
esplanade piétonne, mais ses allées sont des `highway=footway` dans OSM, que le
convertisseur classait en « rue ». Elles ressortaient en gris foncé, et le modèle
y dessinait consciencieusement chaussée, passages piétons et voitures en travers
de la place. Les données étaient bonnes, la traduction était fausse. Une planche
relue avant de générer aurait montré l'erreur en dix secondes.

### 3. `qa.py`

* **Dérive géométrique** : Canny sur la tuile stylisée et sur le squelette, après
  flou léger, avec tolérance de recouvrement en pixels. Rappel (le squelette
  est-il retrouvé ?), précision (le dessin s'appuie-t-il sur le squelette ?), F1.
  Le rappel est la mesure qui compte : le styliseur *doit* ajouter du détail, donc
  faire baisser la précision.
* **Raccords** : bandes de 64 px de part et d'autre de chaque frontière ;
  concordance de l'encre au droit exact de la couture + écart de densité.
* `qa_out/report.html` (vignettes, tableaux triés du pire au meilleur, liste des
  tuiles à refaire) et `qa_out/scores.json`.

### 4. `assemble.py`

Mosaïque PNG pleine résolution puis vectorisation en un seul calque « décor »
(vtracer par défaut, potrace en repli). L'image est réduite avant vectorisation
(`--vector-max-px`, 8000 par défaut) : tracer 12 288 × 8 192 directement est
inutilement lourd.

### 5. `characters.py`

Non commencé — attend votre accord.

## Coûts

`pricing.json` contient les tarifs utilisés pour le calcul. **Ils ne sont pas
vérifiés** : la page de tarification officielle est inaccessible depuis cet
environnement. Le montant affiché est calculé à partir des tokens réellement
renvoyés par l'API, mais le tarif au token reste à confirmer. Le garde-fou
`--budget-eur` s'applique quoi qu'il arrive.

Ordre de grandeur, aux tarifs supposés : ~0,14 € par tuile 2K, soit ~0,3 € pour le
test 1×2 et ~3,4 € pour la grille complète 6×4.

## Tests

```bash
make test     # 70 tests
make check    # pyflakes
```

Couvrent la projection lat/lon, l'orthonormalité et l'élévation du repère caméra,
la jointivité des tuiles et le partage exact des coins entre voisines, l'ordre de
rendu, l'assemblage et la renumérotation du prompt, et les métriques de QA
(dérive détectée sur une géométrie décalée, raccord parfait sur une image coupée
en deux), le cycle export / import du mode manuel et la mesure de densite. Aucun test n'exige
Blender ni le réseau.

## Sécurité

`GEMINI_API_KEY` est lue dans l'environnement, jamais écrite dans le dépôt ni dans
les logs : les messages d'erreur sont expurgés avant affichage (`gemini._safe`).
