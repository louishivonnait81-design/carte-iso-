# 003 — Les îlots sortent en rubans, pas en masses

**Ce qu'on voit.** Une bonne moitié des volumes sont des U, des L et des lames
étroites au lieu de pâtés pleins. Deux causes, mesurées séparément :

1. les emprises OSM d'un centre ancien forment des **anneaux** autour de
   courettes. `COUR_MIN_M2` en comble déjà une partie — il a fallu le faire
   *avant* de soustraire les chaussées, sans quoi la cour n'est plus un trou
   mais une encoche ;
2. il reste les **impasses `residential`**, que OSM trace à l'intérieur des
   îlots et qui les entaillent jusqu'au cœur. `RUE_MIN_LARGEUR` ne les attrape
   pas : elles sont larges.

**Ce qu'on veut.** Un îlot MicroMacro est une masse pleine bordée de rues. Les
impasses et les cours ne devraient pas le découper, seulement les voies
TRAVERSANTES.

**Comment on saura.** Deux chiffres. La part des volumes dont
`buffer(-4) ` n'est pas vide (aujourd'hui à mesurer, viser > 80 %), et le
rapport `aire / aire du rectangle englobant` médian, qui doit monter au-dessus
de 0,55.

**Piste.** Ne garder pour découper que les voies dont les deux extrémités
touchent une autre voie du même jeu — un graphe, pas une liste de segments. Une
impasse a une extrémité libre.
