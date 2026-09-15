# 002 — Toit à quatre pans pour les volumes de plus de 200 m²

**Ce qu'on voit.** `GABLE_MAX_M2` vaut 200, donc tout volume plus grand demande
une croupe — mais la croupe se fabrique par `inset_region` en offset « even »,
qui divise le décalage par `sin(angle/2)` : sur une pointe, un sommet part à
l'autre bout de la carte. Le constructeur détecte le débordement et retombe sur
un faîtage. Résultat réel : 104 faîtages pour 28 croupes, alors que la règle en
demandait l'inverse.

**Ce qu'on veut.** Une vraie croupe sur les grands volumes : quatre pans qui se
rejoignent sur un faîtage court, sans dégénérer sur une emprise irrégulière.

**Comment on saura.** Le compte affiché par `build_blender.py` : au moins 80 %
des volumes de plus de 200 m² sortent en `hip`, et aucun objet ne déborde de son
emprise de départ de plus de 0,5 m (le contrôle existe déjà dans `poser_toit`).
