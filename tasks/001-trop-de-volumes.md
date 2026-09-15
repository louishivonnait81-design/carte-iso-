# 001 — 417 volumes pour une cible de 60 à 150

**Ce qu'on voit.** `generalize.py` annonce `239 îlots → 405 volumes` plus
12 monuments. La cible du README est 60 à 150.

**Le piège.** Monter `M2_PER_VOLUME` ne suffira pas : **on ne fait jamais moins
de volumes que d'îlots**, et il y en a 239. À 450 m²/volume on obtient 405 ; à
900, on descend vers 239 et on s'arrête là.

**Ce qui commande vraiment le compte**, mesuré sur une variante du script :

| levier | îlots |
|---|---|
| tel quel | 239 |
| ne laisser découper que les voies d'au moins 6,5 m (les sentiers et les venelles de service ne bornent pas un îlot) | 153 |
| + souder les mitoyens à 3 m au lieu de 0,6 (`MERGE_GAP`) | 113 |
| + jeter les volumes sous 250 m² | 101 |

**Comment on saura.** La ligne affichée par `generalize.py` tombe entre 60 et
150, et la place Jean-Jaurès est toujours bordée de volumes distincts — la
généralisation ne doit pas avaler le repère principal de la carte.
