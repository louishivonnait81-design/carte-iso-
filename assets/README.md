# Assets

Fichiers attendus ici, **absents du dépôt** à ce jour :

| Fichier | Rôle |
|---|---|
| `REF_01_style.png` | Bible de style — le **trait**, jamais l'architecture. Jointe à chaque appel image. |
| `REF_02_castres.png` | Architecture castraise dans le même trait. Produit par `make ref02`, à valider avant usage. |
| `castres.osm` | Extrait OpenStreetMap du vieux Castres, téléchargé dans un navigateur. **C'est la source de la géométrie.** |
| `tests/` | Tuiles de test déjà produites et résultat Nano Banana v2, niveau de qualité visé. |

`castres.blend` n'est pas suivi par git : `make blend` le reconstruit depuis
`castres.osm` en une quarantaine de secondes. `ref02_candidates/` et les copies
carrées des références (`square/`) sont ignorés de même.

```bash
make blend      # castres.osm -> castres.blend
make render     # -> tiles/
make planche    # relire les données avant de générer
```
