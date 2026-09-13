# MicroMacro Castres

Carte de jeu type *MicroMacro Crime City* du vieux Castres : vue isométrique 30°,
trait noir sur blanc pur, style cartoon ligne claire. **La géométrie vient de
Blender / OpenStreetMap ; l'IA générative ne fait que le style.** Toute dérive de
géométrie est un défaut mesuré par `qa.py`, pas une fatalité.

Les personnages viendront plus tard, sur un calque séparé (`characters.py`, non
commencé).

## État du dépôt

Le squelette du pipeline est en place et testé. **Trois choses manquent pour
pouvoir produire une seule tuile :**

| Manquant | Où | Conséquence |
|---|---|---|
| `assets/REF_01_style.png` | à déposer | aucun habillage possible (bible de style) |
| `assets/castres.blend` | à déposer | aucun rendu possible (géométrie Blosm) |
| `GEMINI_API_KEY` | variable d'environnement | seulement pour le mode API ; **inutile en mode manuel** |

`assets/tests/` (tuiles de test + résultat Nano Banana v2) est également absent.
Voir `assets/README.md`.

## Zone

* Vieux Castres : bd Léon Bourgeois (O) → Agout / bd Raymond Vittoz (E),
  bd Miredames (N) → bd Henri Sizaire (S), jardin de l'Évêché inclus.
* Import Blender avec 150 m de marge : lat 43.6010 → 43.6095, lon 2.2335 → 2.2485.
* Centre de la grille : **43.6052 / 2.2405**.
* Grille par défaut : **6 colonnes × 4 lignes**, tuiles de **180 m** de large à
  l'écran, **2048 px** chacune → carte finale **12 288 × 8 192 px**.

## Installation

```bash
make install                    # dépendances Python (3.11)
make test                       # 28 tests, ni Blender ni réseau requis
export GEMINI_API_KEY=...       # mode API seulement — jamais dans le dépôt
```

### Blender

`render.py` cherche Blender dans cet ordre : `$BLENDER_BIN`, `blender` dans le
PATH, `third_party/blender*/blender`, puis le module pip `bpy`.

> Dans l'environnement d'exécution distant utilisé pour développer ce dépôt,
> `download.blender.org` est **bloqué par le proxy réseau** : le tarball officiel
> n'est pas téléchargeable ici. PyPI reste accessible, donc `pip install bpy`
> fonctionne (bpy ≥ 4.1 pour Python 3.11). Sur une machine locale, préférer
> Blender 3.6 LTS, la version d'origine de la scène.

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
tenir le prompt** : le texte y renvoie par numéro. `import` vérifie au passage que
l'image rendue est bien carrée — si Gemini a recadré, le raccord sera décalé.

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
leur nom, celui de leurs collections et leurs propriétés personnalisées (Blosm y
recopie les tags OSM). Le nommage exact de `castres.blend` n'ayant pas pu être
inspecté, **commencer par `--dump-categories`** pour vérifier le classement, et
ajuster `DEFAULT_RULES` en tête de `scripts/iso_tiles.py` si besoin.

| catégorie | couleur | note |
|---|---|---|
| bâtiment | gris clair | |
| rue / trottoir | gris foncé | les courbes Blosm sont élargies en rubans plats (`--road-width`) |
| végétation | vert | |
| **eau** | **bleu** | **ajout** au cahier des charges, voir ci-dessous |
| sol ouvert | blanc | plan de sol ajouté sous toute la grille |

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
* Cache disque + reprise : une tuile déjà produite n'est **jamais** écrasée sans
  `--force` ; si ses entrées ont changé depuis, le message le signale.
* Retries avec backoff exponentiel et jitter sur les erreurs transitoires.
* Coût estimé par appel et cumulé, journalisé dans `styled/<tuile>.json` et
  `styled/.budget.json`.
* **Plafond de dépense** : `--budget-eur 5` par défaut ; le script s'arrête avant
  de dépasser et demande de relancer avec un plafond explicite.
* `--dry-run` écrit les prompts dans `styled/prompts/` sans appeler l'API.

**Le prompt** est dans `prompts/stylize_v2.md`, découpé en sections
(`base`, `water`, `ref02`, `left`, `top`). Les renvois aux images y sont des
variables (`{lines}`, `{sem}`, `{left}`…) et non des numéros écrits en dur : quand
REF_02 s'ajoute, tout se renumérote automatiquement. C'est le seul écart au texte
fourni, et il est couvert par les tests (`tests/test_prompt.py`).

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
make test     # 28 tests
make check    # pyflakes
```

Couvrent la projection lat/lon, l'orthonormalité et l'élévation du repère caméra,
la jointivité des tuiles et le partage exact des coins entre voisines, l'ordre de
rendu, l'assemblage et la renumérotation du prompt, et les métriques de QA
(dérive détectée sur une géométrie décalée, raccord parfait sur une image coupée
en deux), ainsi que le cycle export / import du mode manuel. Aucun test n'exige
Blender ni le réseau.

## Sécurité

`GEMINI_API_KEY` est lue dans l'environnement, jamais écrite dans le dépôt ni dans
les logs : les messages d'erreur sont expurgés avant affichage (`gemini._safe`).
