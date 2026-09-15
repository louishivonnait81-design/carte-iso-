# 002 — 353 toits plats sur 405

**Ce qu'on voit.** 87 % des volumes sortent en toit plat, 13 % en pignon. Un
centre ancien tout en terrasses.

**Pourquoi.** `GABLE_MAX_AREA` vaut 220 m² : au-delà, pas de pignon. Or la
médiane d'un volume est bien au-dessus. Et la croupe classique, par
`inset_region` en offset « even », ne peut pas la remplacer : elle divise le
décalage par `sin(angle/2)` et, sur une emprise en L ou en pointe, envoie un
sommet à l'autre bout de la carte.

**Ce qui marche**, éprouvé dans `v2/06_toits.py` : un **faîtage qui ne construit
rien**. On coupe la face du dessus le long de son axe long (`bisect_plane`) et
chaque sommet remonte selon sa distance à cet axe. Aucun sommet ne bouge dans le
plan, donc aucun angle rentrant ne peut replier quoi que ce soit. Cela a fait
passer `v2/` de 70,6 % à 25,7 % d'acrotères.

Garder la croupe pour les emprises ramassées, mais **constater** son
débordement après coup (comparer la boîte englobante avant/après ; au-delà de
0,5 m, refaire un faîtage) plutôt que d'essayer de le prévoir : le bâtiment
83182684 est convexe, remplit 0,86 de son rectangle, n'a aucun angle sous 78°,
et son sommet partait à 141 m.

**Comment on saura.** Le compte des toits : moins de 30 % de plats.
