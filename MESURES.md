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

## v2 — pourquoi une ruelle n'est pas visible

Mesure sur la zone du coeur (220 m), grille de 25 cm, `v2/jouabilite.py`. Une
traversee de ruelle est **jouable** si le sol qui y reste DEGAGE atteint 2,5 m.

La largeur au sol ne suffit pas a repondre. La camera regarde du sud-ouest a
60 degres : un mur de hauteur h avale 0,408 h de largeur apparente. Avec les
10,0 m de hauteur moyenne de l'import, ce sont **4,1 m avales** — une ruelle de
4 m n'a plus un pixel de sol, a n'importe quelle resolution. C'est pourquoi le
rendu a 8000 px ne reglait rien.

Une premiere mesure comptait aussi les courettes fermees au milieu des ilots
parmi les ruelles noires : elles faisaient un tiers du defaut, et personne ne
peut y entrer. Le sol libre est donc d'abord rempli depuis le bord de la zone.

| etat | NS jouable | NS noire | EO jouable | EO noire | sol libre visible |
|------|-----------|----------|-----------|----------|-------------------|
| retrait 1,2 m uniforme | 73,1 % | 13,7 % | 64,8 % | 14,5 % | 82,4 % |
| soudure 2,5 + retrait 2,0 par axe + hauteurs x0,7 | **84,1 %** | **6,8 %** | **88,3 %** | **2,9 %** | **88,9 %** |

Le chiffre qui compte est ailleurs dans le tableau. En separant les traversees
selon qu'elles longent une RUE (entre deux ilots) ou une fente INTERIEURE a un
ilot :

| | avant : traversees / noires | apres : traversees / noires |
|---|---|---|
| entre deux ilots (les rues) | 2804 / 161 | 2521 / **0** |
| a l'interieur d'un ilot | 1860 / 923 | 1657 / 696 |

**85 % des traversees invisibles n'etaient pas des rues** — 93 % sur le seul axe
nord-sud, celui dont vous disiez qu'il devait se voir partout. Le retrait d'ilot ne
pouvait rien pour elles : l'ilot se contracte d'un bloc. Ce qui les a ouvertes
ou fermees est autre chose.

### Ce que chaque levier a change

* **Soudure des fentes interieures** (2,5 m) : 686 murs recolles. Deux maisons
  mitoyennes saisies dans OSM avec 40 cm d'ecart ne sont pas une ruelle.
* **Retrait AXE PAR AXE** : la mise a l'echelle uniforme reculait un ilot
  allonge de 1,2 m dans sa longueur mais de **0,24 m** dans sa largeur. Les
  ruelles qui longent un ilot ne gagnaient presque rien — exactement celles que
  l'oeil ne voyait plus.
* **Hauteurs x0,7** (10,0 -> 7,1 m de moyenne) : seul levier qui ouvre
  l'interieur des ilots, la ou le plan ne peut rien. Un facteur et non un
  plafond : a plafond 7 m, toutes les maisons se retrouvent a la meme hauteur et
  la ligne de toits s'aplatit, pour un gain de jouabilite identique.
* **Monter la camera** a 65 ou 70 degres gagnerait encore 2 a 6 points, mais les
  rues sont deja jouables a 100 % : l'angle reste a 60 degres, ou la facade se
  voit encore.
* Surface batie 34,4 -> 30,9 % du sol. C'est le prix, et il est assume.
