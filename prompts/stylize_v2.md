<!--
Gabarit du prompt d'habillage. Chaque section commence par un marqueur HTML
"@section" suivi de son nom, sur sa propre ligne (voir plus bas). stylize.py
assemble : base + architecture [+ notes] [+ water] [+ ref02] [+ left] [+ top].

Les references aux images sont des variables ({Ref01}, {lines}, {sem}, {left},
{top}) et non des numeros ecrits en dur : l'ordre reel des images envoyees
depend de la presence de REF_02 et des voisines deja stylisees, la numerotation
doit donc suivre. Elles sont remplacees par "Image N" / "image N".
-->

<!-- @section base -->
{Ref01} is the style reference. {Lines} is a line drawing of a real city block in
strict isometric projection. {Sem} is the same view with flat colors telling you
what each surface is: light gray = building, dark gray = street or sidewalk,
green = planted strip or vegetation, white = open ground, square or courtyard.

Redraw {lines} in exactly the LINE STYLE of {ref01}: hand-inked cartoon, black ink on
pure white, uniform line weight, no shading, hatching, gray or color, no text.

ARCHITECTURE: this is Castres, a small historic town in south-west France — NOT
Paris. Even simplified, buildings must look like Castres: old half-timbered houses
with overhanging upper floors along the river, plastered façades with hinged
shutters, low-pitched roofs with curved terracotta tiles, 17th–18th century stone
mansions, stone quays and bridges. Do NOT draw Haussmann
apartment blocks, mansard zinc roofs or Parisian wrought-iron balconies; use
{ref01} only for the ink style, never for the architecture.

NON-NEGOTIABLE RULES: (1) Every structure stays exactly where it is — same
footprint, same height, same angle. (2) EVERY light gray shape in {sem} must
become a fully detailed building with windows, doors and a roof — no box may remain
blank. (3) Never place a building on dark gray or white areas; streets stay streets,
white areas stay open ground. (4) Fill the image edge to edge, no border, margin or
vignette. (5) Output square, 2K resolution or higher.

Add only surface detail: façade windows with shutters and doors, small shopfronts
with awnings on ground floors, tiled roofs with chimneys, curbs, crosswalks and lane
markings on streets, a few parked cars, plane trees and benches on green and white
areas, lampposts, a café terrace with tables.

<!-- @section architecture -->
Every BUILDING in this drawing was built between 1400 and 1800; there is no
building later than 1800. The STREET LIFE, however, is today's: parked cars, café
terraces, modern lampposts, road markings. No horse carts, no period costumes.

NO PEOPLE, NO ANIMALS, NO FIGURES OF ANY KIND — the characters are added later
on a separate layer. Streets and squares are empty of people.

NO INVENTED LANDMARKS. Landmarks exist only where {lines} shows their footprint:
the cathedral only where {lines} shows a very large building with a distinct
outline, the river and its bridges only where {sem} shows blue. Never draw water,
a church, a tower or a spire where {lines} and {sem} show ordinary houses.

CLOSED LIST OF BUILDING TYPES. Every single building belongs to one of these three
types and to no other. There is no fourth type:
  TYPE A — half-timbered house on the river: exposed timber frame, corner posts,
    one sill beam and one or two diagonal braces per façade, upper floor clearly
    overhanging on visible corbels, ground floor rising straight out of the water
    on stone footings.
  TYPE B — plastered town house: plain rendered façade, no visible frame or
    coursing, a simple moulded string course between floors at most.
  TYPE C — stone mansion (hôtel particulier): ashlar façade with quoins at the
    corners, one round-arched carriage porch, slightly taller than its neighbours.

RULES THAT APPLY TO EVERY BUILDING WITHOUT EXCEPTION:
  - two or three storeys, never more, never a single-storey shed;
  - the roof is pitched with a visible ridge, low slope, curved terracotta canal
    tiles, and a génoise cornice of two stacked tile courses under the eaves;
    no roof is flat, no roof is a terrace with a parapet;
  - every window is rectangular, taller than wide, with two hinged wooden
    shutters, and nothing else — no glazing bars, no reveals, no bay windows;
  - chimneys are plain rendered or brick stacks on the ridge.

NOTHING IN THIS DRAWING IS MODERN. No glass, no metal, no concrete, no steel
railing, no flat roof, no garage door, no shopfront window, no solar panel, no
air conditioner, no car park marking, no modern street furniture. If you are
unsure how to draw something, copy the nearest building rather than inventing.

<!-- @section notes -->
WHAT IS REALLY HERE. This tile shows a real part of the old town of Castres
(Tarn, France). Use what you know of these real places and draw them as they
actually look, each at its position in {lines}:
{notes_list}
Give every listed shop the shopfront described for it, and make each one clearly
DIFFERENT from its neighbours at a glance — a passer-by should be able to tell the
baker from the butcher without reading anything. Signs, awnings and hanging brackets
may carry a drawn emblem (a pretzel, a boot, a pair of scissors) but NEVER a letter,
a word or a number, here or anywhere else in the image.

This list tells you WHAT stands here. It never tells you WHERE, HOW BIG or HOW MANY:
those come from {lines} and from {lines} alone. Do not compose a square, a street or
a row of buildings of your own — trace the shapes that are in {lines}, at their size
and their angle, and put the listed things on them. If the list mentions trees, a
statue or stalls, draw them only where {lines} shows something to draw them on.

<!-- @section water -->
In {sem}, blue marks water: the river Agout and its mill races. Draw water as calm
ripple lines between stone quays, never as a building or a street.

<!-- @section ref02 -->
{Ref02} is a second reference showing the ARCHITECTURE of Castres in this same ink
style: half-timbered houses on the river, plastered façades with shutters, curved
terracotta roofs. Take the buildings from {ref02} and the ink style from {ref01}.

Two things {ref02} gets wrong, do not copy them: draw trees as isometric canopies
seen from above at the SAME angle as the buildings, standing on no base plate,
never as flat front-view lollipops; and give every roof a visible pitch with a
ridge — low-pitched, but never flat and never a terrace with a parapet.

<!-- @section left -->
{Left} is the finished tile directly to the LEFT of this one. Your drawing must
continue it seamlessly: every street, building and line touching the left edge of
this tile must match {left}'s right edge exactly, same line weight, same level
of detail.

<!-- @section top -->
{Top} is the finished tile directly ABOVE this one. Your drawing must
continue it seamlessly: every street, building and line touching the top edge of
this tile must match {top}'s bottom edge exactly, same line weight, same level
of detail.
