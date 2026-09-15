# 003 — L'angle de la caméra : 41°, pas 35,26°

**Ce qu'on voit.** `ISO_TILT = 54.7356` dans `build_blender.py`, c'est-à-dire
l'isométrie vraie : 35,26° au-dessus de l'horizon.

**Ce que dit la référence.** Mesuré sur une photo de la planche MicroMacro :
**41°**. Méthode et contrôle dans `v2/mesure_reference.py` — dans une projection
orthographique, deux directions du sol perpendiculaires tombent sur la page à
des angles a1 et a2 tels que `|tan a1 × tan a2| = sin²(élévation)`,
indépendamment de l'orientation du bâtiment. Sur la grille de toiture du grand
bâtiment ouvert : +14° et −61°. Le script rejoue le contrôle sur des planches de
synthèse tracées à 40 / 35 / 55° et retrouve 40,1 / 35,3 / 55,6.

C'est aussi ce qui explique l'asymétrie de la planche : elle n'est **pas** une
isométrie symétrique à 45°, le bâtiment mesuré est à 21° d'azimut.

**Ce qu'on veut.** `ISO_TILT = 49.0`.

**Le prix, mesuré.** L'ombre portée d'un mur passe de 0,408 h à 0,814 h — le
double. Sur `v2/`, adopter 41° sans rien d'autre faisait tomber les traversées
de ruelle jouables de 84 % à 76 % (nord-sud) et de 88 % à 64 % (est-ouest). Ce
qui compense n'est pas l'angle mais la **hauteur** : `MAX_LEVELS=3` à 3,2 m fait
des murs de 9,6 m, là où `v2/` a dû descendre à 4,6 m pour que les ruelles
restent lisibles.

**Comment on saura.** À l'œil sur `castres.png` : les façades doivent se voir
sans que les rues étroites se referment. `v2/mesure_rues.py` sait chiffrer la
largeur dégagée si on veut trancher autrement qu'à l'impression.
