<!--
Gabarit du prompt d'habillage. Les sections sont delimitees par
`<!-- @section nom -->`. stylize.py assemble : base [+ water] [+ left] [+ top].

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
mansions, a Gothic cathedral, stone quays and bridges. Do NOT draw Haussmann
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

<!-- @section water -->
In {sem}, blue marks water: the river Agout and its mill races. Draw water as calm
ripple lines between stone quays, never as a building or a street.

<!-- @section ref02 -->
{Ref02} is a second reference showing the ARCHITECTURE of Castres in this same ink
style: half-timbered houses on the river, plastered façades with shutters, curved
terracotta roofs. Take the buildings from {ref02} and the ink style from {ref01}.

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
