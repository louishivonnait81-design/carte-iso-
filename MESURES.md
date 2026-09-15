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

## v2 — les toitures

Tout en toits-terrasses. 187 batiments sur 264 recevaient un acrotere, dans un
coeur de ville ancienne. En comptant les causes d'echec du test de croupe :

| cause de l'echec | batiments |
|---|---|
| angle rentrant, seul | 42 |
| trop etroit, seul | 24 |
| angle rentrant + remplissage (+ autre) | 79 |
| plus de 10 sommets, toujours avec un angle rentrant | 29 |

L'angle rentrant domine, et c'est logique : la croupe se fabrique par inset, et
un inset se replie dans un L. Un faitage, lui, ne construit rien — on coupe la
face du dessus le long de l'axe long et chaque sommet remonte selon sa distance
a cet axe. Acroteres 70,6 -> 25,7 %, faitages 0 -> 58,5 %, croupes 28,7 -> 15,5 %.

### Huit objets a 250 m de la zone

Freestyle tirait de longues diagonales en travers de la carte. Tous nes du meme
endroit : l'inset "even" de l'acrotere, qui divise le decalage par sin(angle/2).
Sur une emprise en lame de couteau — une epaisseur de mur saisie comme un
batiment — il envoie les sommets a l'autre bout du monde.

| correction | objets hors zone | pire ecart |
|---|---|---|
| avant | 8 | 253,8 m |
| offset simple, epaisseur bornee a 0,25 x la petite cote | 1 | 5,5 m |
| + controle du debordement apres inset, repli sur le faitage | **0** | — |

Le neuvieme resistait a tous les criteres de forme : le batiment 83182684 est
convexe, remplit 0,86 de son rectangle englobant, n'a aucun angle sous
78 degres — et son sommet partait a 141 m. On ne le prevoit donc pas, on le
constate. Un garde-fou d'angle minimal, ajoute en chemin, s'est ensuite revele
sans effet : il a ete retire plutot que garde par prudence.

## v2 — quels toits ouvrir

137 POI dans la zone, dont 100 d'interieur une fois retires les bancs, les
corbeilles, les arceaux a velos et les cameras. Rapportes aux emprises par
test point-dans-polygone : **48 batiments sur 237 en contiennent au moins un**,
soit un sur cinq ; 46 en ont un seul, un en a deux, un en a trois.

Un sur cinq, c'etait trop pour "il y en a que certains". Dix lieux sont ouverts,
choisis par poids du commerce multiplie par la racine de l'emprise, avec 35 m
minimum entre deux pour qu'ils ne se regroupent pas dans un coin.

### Ce qu'il a fallu pour qu'une ouverture SE VOIE

Retirer le versant ne suffit pas. Trois rendus ont ete necessaires.

| etat | ce que l'oeil lit |
|---|---|
| versant retire, plancher a l'egout | un toit-terrasse : un plan blanc borde d'un trait |
| + epaisseur de mur de 0,35 m | un toit-terrasse a acrotere. Toujours pas un interieur |
| + refends tous les 4,5 m | une piece cloisonnee, lisible |

Deux pieges en chemin, tous deux visibles seulement au rendu :

* des refends poses sur les axes du monde donnent un DAMIER sur une maison de
  biais — cela se lit comme un entrepot. Ils suivent l'axe propre du batiment,
  obtenu par analyse en composantes principales du plancher ;
* un refend monte sous le versant CONSERVE le traverse et seme des traits en
  travers de la toiture. On coupe donc d'abord le plancher a la limite du
  decouvert : sans cette coupe, chaque refend traversait la piece de part en
  part, son milieu tombait pile sur le faitage, et six refends sur sept
  disparaissaient au test.

Part de l'emprise laissee a ciel ouvert : de 23 % (la poissonnerie, dont un seul
pan sur quatre regarde la camera) a 73 % (la boite de nuit), mediane 55 %.

## La reference, enfin mesuree

Trois photos de la planche MicroMacro. Jusque-la, tout ce qui touchait au STYLE
etait deduit par raisonnement : l'angle de camera, les epaisseurs de trait,
l'echelle du personnage. Rien n'etait mesure sur la reference.

### L'angle de vue

Dans une projection orthographique, deux directions du sol perpendiculaires
tombent sur la page a des angles a1 et a2 tels que
`|tan(a1) x tan(a2)| = sin^2(elevation)`, **independamment de l'orientation du
batiment mesure**. Il suffit donc des deux bords d'une meme toiture.

Sur la grille de toiture du grand batiment ouvert (photo 1), les deux familles
tombent a **+14** et **-61 degres** — verifie a l'oeil en tracant les deux
familles par-dessus, `--verifier`, parce qu'aucune statistique ne sait laquelle
des paires proposees appartient au meme toit. D'ou :

| | valeur |
|---|---|
| elevation de MicroMacro | **41 degres** (40,1 a 42,1 selon qu'on lit -59 ou -61) |
| ma carte | 60 degres |
| azimut du batiment mesure | 21 degres — la planche n'est donc PAS une isometrie symetrique a 45 |

Deux estimateurs ont ete ecrits et jetes avant celui-la, et c'est le controle
sur planche de synthese qui les a demasques : un histogramme d'orientation de
gradient annoncait des familles a +-53 degres sur un dessin trace a +-30 (les
croisements de traits l'abusent), et un spectre de Fourier se laissait ecraser
par le pli du papier. La version retenue (rotation + nettete du profil, un
Radon du pauvre) retrouve 40,1 / 35,3 / 55,6 sur des planches tracees a 40 / 35
/ 55. `v2/mesure_reference.py --test` rejoue ce controle.

### Ce que l'angle de la reference couterait a ma carte

| elevation | NS jouable | NS noire | EO jouable | EO noire | sol visible |
|---|---|---|---|---|---|
| 60 deg (ma carte) | 84,1 % | 6,8 % | 88,3 % | 2,9 % | 88,9 % |
| 50 deg | 79,3 % | 8,4 % | 81,5 % | 9,0 % | 84,3 % |
| **41 deg (reference)** | 75,8 % | 16,8 % | 63,8 % | 18,7 % | 78,8 % |

L'ombre d'un mur passe de 0,408 h a 0,814 h : exactement le double. A hauteur
egale, adopter l'angle de la reference annule le gain de jouabilite de
l'etape 5b.

### Le trait et l'encre

| | reference (photos 1 et 2) | ma carte a 4000 px |
|---|---|---|
| densite d'encre, quartier dense | 15,0 - 15,7 % | 15,3 % |
| epaisseur mediane | 2 px | 4 px |
| rapport p90 / mediane | 2,00 | 2,00 |

La hierarchie du trait est donc du bon ordre — la reference n'est pas d'epaisseur
uniforme, contrairement a ce que l'oeil croit d'abord.

### Ce que les photos disent sans qu'on ait a mesurer

* **L'interieur d'un batiment ouvert est un PLAN d'un seul niveau**, cloisonne
  par des refends bas, meuble, et peuple. C'est exactement ce que fait
  l'etape 11 — les refends tous les 4,5 m ne sont pas une invention gratuite.
* **Le toit n'est pas retire en entier** : sur le grand batiment de la photo 1,
  la partie eloignee de la camera est conservee avec sa grille de panneaux, la
  partie proche est ouverte. Le choix "seul le versant qui regarde la camera"
  est celui de la reference.
* **Le personnage fait environ 28 px pour un entre-rang de fenetres de 50 px**,
  soit 0,55 niveau : le dessin est a l'echelle humaine reelle, 1,7 m pour 3 m
  d'etage.
* **La densite de vie est d'un autre ordre** : chaque bloc porte des dizaines de
  personnages, de vehicules et d'objets. Ma carte en compte 57 pour toute la
  zone.

## Ce que la reference a change dans la config

| parametre | avant | apres | ce qui l'a decide |
|---|---|---|---|
| elevation | 60 deg | **41 deg** | mesure sur la planche (+14 / -61 sur une meme toiture) |
| echelle_hauteur | 0,70 | **0,45** | a 41 deg l'ombre d'un mur double ; 4,6 m de mur moyen rend les 80 % de traversees jouables |
| epaisseurs | 2,2 / 1,0 / 0,8 / 0,55 | **1,5 / 1,0 / 0,8 / 0,6** | profil de la reference retrouve exactement |
| largeur_reference_px | — | **8000** | Freestyle compte en pixels absolus : sans cela un apercu ment sur le trait |

### Le trait, mesure a echelle egale

Le rendu a 7000 px donne 50 px par etage, exactement comme la photo : la
comparaison a enfin un sens.

| | encre | p25 | p50 | p75 | p90 | p90/p50 |
|---|---|---|---|---|---|---|
| reference, photo 1 | 15,7 % | 2 | 2 | 3 | 4 | 2,00 |
| reference, photo 2 | 15,0 % | 2 | 2 | 3 | 4 | 2,00 |
| ma carte, masses 2,2 | 8,5 % | 2 | 2 | 5 | 7 | 3,50 |
| **ma carte, masses 1,5** | 5,6 % | **2** | **2** | **3** | **4** | **2,00** |

Trois jeux d'epaisseurs (1,5 / 1,2 / 1,0 en masse) donnent le meme profil : la
mesure ne les distingue pas. On garde le plus contraste, 1,5, parce que c'est la
ligne de masse qui fait lire un pate de maisons.

**Ce que le trait ne reglera pas** : la densite. 5,6 % d'encre contre 15,0 %.
L'ecart n'est pas dans l'epaisseur mais dans le CONTENU — la planche porte des
dizaines de personnages, de vehicules et d'objets par bloc, ma carte en compte
57 pour toute la zone. C'est le prochain ecart a combler, et le seul qui reste
visible a l'oeil nu sur le rendu.

## Peupler : ce que 502 objets changent, et ce qu'ils ne changent pas

L'ecart de densite avec la reference — 5,5 % d'encre contre 15,7 % a echelle
egale — ne pouvait pas se regler au trait. Etape 12 : vehicules le long des
voies carrossables, terrasses devant les cafes, etals devant les commerces,
velos aux arceaux. Tout depuis OSM, rien de pose au hasard : un emplacement est
refuse si ses quatre coins ne tombent pas sur du sol libre, teste sur la grille
de 25 cm des emprises reelles.

| etat | objets de rue | encre, quartier dense | encre, la place |
|---|---|---|---|
| avant | 57 | 5,54 % | 3,72 % |
| + 511 objets de vie | 568 | 6,28 % | 4,85 % |
| + trame de facade corrigee | 568 | 6,55 % | — |
| final, sans les empilements | 559 | **6,50 %** | **4,77 %** |
| reference MicroMacro | — | **15,71 %** | — |

**Peupler la rue n'a comble qu'un cinquieme de l'ecart.** C'est une mesure utile
parce qu'elle contredit l'intuition : on croyait le vide dans les rues, il est
sur les TOITS. A 41 degres et 4,6 m de mur, la toiture occupe la plus grande
part de la page, et elle est nue.

### Un defaut trouve en chemin

L'ecrasement des hauteurs de l'etape 5b ne s'appliquait pas a la trame de
facade : une maison ramenee a 4,6 m ne recevait plus qu'UNE rangee de fenetres,
`(4,6 - 0,6) // 3,2 = 1`. Tout ce qui est vertical dans la facade suit desormais
`echelle_hauteur`, l'entraxe des travees restant horizontal. Ouvertures posees :
4 375 -> 9 136.

### Deux voies OSM, un seul carrefour

Chaque voie deposait son vehicule au meme carrefour : le premier rendu montrait
des voitures empilees. Une distance minimale de 4,5 m entre deux vehicules en
retire 9 sur 127.
