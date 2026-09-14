# Mesures

Journal des chiffres qui ont decide quelque chose. Les dessins eux-memes ne sont
pas suivis par git (`drawn/`, `units/`, `manual_units/`), et les messages de
commit racontent chacun une correction sans donner la suite. Ce fichier donne la
suite.

Regle : on n'inscrit ici que ce qui a ete mesure, jamais une impression.

## Pourquoi le pipeline a change d'architecture

Habillage par TUILE : le modele recevait le squelette d'une tuile entiere et le
redessinait. Six iterations de prompt, deux modeles.

| tuile     | derive | rappel / hasard | note |
|-----------|--------|-----------------|------|
| tile_1_4 v1 | 0,000 | 0,347 / 0,403  | place composee, 25 % d'aplats gris |
| tile_1_4 v2 | 0,000 | 0,428 / 0,468  | riviere et pont inventes (bug `has_water`) |
| tile_1_4 v3 | **0,461** | 0,817 / 0,661 | meilleur resultat obtenu |

Le v3, pourtant le meilleur, posait **34,8 % de son encre hors de toute emprise
batie** — deux maisons entieres en pleine place. Dans le quart haut-gauche, OSM
donne 83 % de sol ouvert et le dessin y encrait 28 % des pixels, contre 44 % sur
du bati reel.

Conclusion : le modele ne place pas la matiere ou on le lui dit, quelles que
soient les regles ajoutees. On a cesse de le lui demander.

## Habillage par UNITE

Une unite = une rangee mitoyenne (batiments partageant un noeud OSM), coupee a
45 m. 1397 batiments de la grille -> 437 unites, dont 13 sur tile_1_4.

Le compositeur pose chaque dessin a une boite calculee. Controle de chainage,
rendus bruts contre rendu d'ensemble : **decalage dx=0 dy=0**, concordance
81,5 %. Les 18 % d'ecart sont des aretes cachees, verifiees a l'oeil.

| unite      | IoU brut | IoU cale | encre rognee | gris a 15 % |
|------------|----------|----------|--------------|-------------|
| u83180702  | 0,888    | 0,889    | 12,2 %       | 21,7 %      |
| u83181573  | 0,857    | **0,914** | 8,3 %       | 18,0 %      |
| u83180512  | 0,897    | **0,924** | 10,1 %      | 20,8 %      |
| u83184162  | 0,817    | **0,861** | 13,9 %      | 22,4 %      |

u83181573 a ete refaite : premiere version 0,833, avec 26,2 % d'encre rognee
dont 79 % dans le tiers bas — son arcade, la seule chose que sa fiche demandait,
disparaissait au collage.

Reference de style REF_01 : 51,1 % de gris a la reduction. Les trois dessins
sont donc deux fois plus clairs que leur propre reference, la ou le meilleur
rendu par tuile montait a 55,4 %.

La silhouette suffit a identifier une unite : le deuxieme et le troisieme dessin
sont arrives sans etiquette, et l'ecart avec la candidate suivante etait de
0,833 contre 0,734, puis 0,897 contre 0,667.

### Ce que chaque regle a change

* **"THE BOTTOM EDGE IS THE GROUND"**, ajoutee apres u83181573. Le modele
  dessinait l'arcade comme un etage ajoute SOUS le volume, et le masque la
  coupait. Rognage 26,2 % -> 17,6 %, part basse 79 % -> 46 %. Dilater le masque
  n'etait pas la reponse : 20 px n'en recuperaient que 30 %.
* **Variation de hauteur** (hachage de l'identifiant OSM, +/- 1,5 m par pas de
  0,5 m) : unites a hauteur uniforme 95 % -> 43 %. Moyenne 8,02 m contre 8,00 m
  pour le defaut nu, donc l'echelle ne bouge pas.
* **Recalage du dessin sur la silhouette**, a l'import. Les quatre dessins
  sortent du modele 3 a 21 % PLUS GRANDS que le volume donne, et le debord part
  vers le bas : le masque leur coupe le rez-de-chaussee, donc l'arcade. Une
  recherche d'echelle et de decalage, bornee a +/- 14 % et appliquee seulement
  si elle gagne plus de 0,01 d'IoU, ramene le rognage de 16,8 / 17,6 / 27,2 % a
  8,3 / 10,1 / 13,9 %. Le placement de l'unite sur la carte, lui, vient toujours
  de Blender : on ne corrige que l'erreur du modele dans sa propre fenetre.
* **Emprises de moins de 4 m2 ignorees** : 136 polygones — cages d'escalier,
  courettes, epaisseurs de mur — qui sortaient en pics de 12 m.

## Hauteurs : ce que l'on ne sait pas

| provenance | part | confiance |
|------------|------|-----------|
| defaut     | 89,6 % | 0,35 |
| type de batiment | 8,9 % | 0,55 |
| niveaux tagues | 1,4 % | 0,90 |
| mesuree | 0 % | — |

10 valeurs distinctes pour 1397 batiments. Le LiDAR HD de l'IGN corrigerait
cela ; il est inaccessible depuis cet environnement, dont la politique reseau
refuse les serveurs de l'IGN (403 a la passerelle).
