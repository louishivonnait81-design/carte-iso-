# Assets

Fichiers attendus ici, **absents du dépôt** à ce jour :

| Fichier | Rôle |
|---|---|
| `REF_01_style.png` | Bible de style — le **trait**, jamais l'architecture. Jointe à chaque appel image. |
| `REF_02_castres.png` | Architecture castraise dans le même trait. Produit par `make ref02`, à valider avant usage. |
| `castres.blend` | Scène Blender 3.6, données OSM importées par Blosm : bâtiments (meshes, hauteurs réelles), rues (courbes), végétation, eau. |
| `tests/` | Tuiles de test déjà produites et résultat Nano Banana v2, niveau de qualité visé. |

`ref02_candidates/` (propositions générées) est ignoré par git.

Avant le premier rendu, vérifier comment les objets de `castres.blend` sont nommés :

```bash
blender -b assets/castres.blend -P scripts/iso_tiles.py -- --dump-categories
```

et ajuster `DEFAULT_RULES` dans `scripts/iso_tiles.py` si le classement est faux.
