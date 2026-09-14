<!--
Gabarit du prompt d'habillage. Chaque section commence par un marqueur HTML
"@section" suivi de son nom, sur sa propre ligne (voir plus bas). stylize.py
assemble : base + architecture [+ notes] [+ water] [+ anchor | ref02]
[+ left] [+ top].

Les references aux images sont des variables ({Ref01}, {lines}, {sem}, {left},
{top}) et non des numeros ecrits en dur : l'ordre reel des images envoyees
depend de la presence de REF_02 et des voisines deja stylisees, la numerotation
doit donc suivre. Elles sont remplacees par "Image N" / "image N".
-->

<!-- @section base -->
{Ref01} is the style reference. {Lines} is a line drawing of a real city block in
strict isometric projection. {Sem} is a COLOUR-CODED KEY, not a picture to copy. Never
reproduce its colours or its flat shapes; read it, then forget it. It tells you
what each surface is: light gray = building, dark gray = street or sidewalk,
green = planted strip or vegetation, white = open ground, square or courtyard.
Green marks the TREES and planted beds, and they are deliberately absent from
{lines}: draw a tree for each green disc, in your own hand.

In {lines} the line weight carries meaning: THICK lines are the outlines of
buildings and other solid masses, THIN lines are secondary detail such as roof
ridges and hips. Read the thick lines as the shapes that must be respected.

Redraw {lines} in exactly the LINE STYLE of {ref01}: hand-inked cartoon, black ink on
pure white, uniform line weight, no shading, hatching, gray or color, no text.

ARCHITECTURE: this is Castres, a small historic town in south-west France — NOT
Paris. Even simplified, buildings must look like Castres: plastered façades with
hinged shutters, low-pitched roofs with curved terracotta tiles, 17th–18th century
stone mansions. The town's famous half-timbered houses standing in the water, and
its stone quays and bridges, belong to the riverbank alone: draw them only where
{sem} shows blue, and nowhere else. Do NOT draw Haussmann
apartment blocks, mansard zinc roofs or Parisian wrought-iron balconies; use
{ref01} only for the ink style, never for the architecture.

NON-NEGOTIABLE RULES: (1) Every structure stays exactly where it is — same
footprint, same height, same angle. (2) EVERY light gray shape in {sem} must
become a fully detailed building with windows, doors and a roof — no box may remain
blank. (3) Never place a building on dark gray or white areas; streets stay streets,
white areas stay open ground. (4) Fill the image edge to edge, no border, margin or
vignette. (5) Output square, 2K resolution or higher.

FRAMING — as important as the rest. Your drawing covers EXACTLY the same ground as
{lines}, corner to corner. The four corners of your image are the four corners of
{lines}, and every building visible in {lines} is visible in yours, at the same
fraction of the frame. DO NOT ZOOM IN. Do not crop, do not re-centre, do not enlarge
one block to fill the page. {lines} is a small piece of a large map, seen from far
away: buildings are meant to look small, and a wide empty area — a river, a square —
stays wide and empty. The style references are close-up plates drawn at a much
larger scale; copy their ink, never their zoom.

Your ink must reach all four edges of the frame exactly as it does in {lines}. A
building that runs off the edge of {lines} runs off the edge of yours, cut at the
same place — do not pull it back inside, do not leave a white band at the top or the
bottom, do not centre the drawing on the page. And do not close what {lines} leaves
open: a street that leaves the frame keeps going, a square open on one side stays
open on that side. You are not composing a scene, you are inking a fragment.

Add only surface detail: façade windows with shutters and doors, small shopfronts
with awnings on ground floors, tiled roofs with chimneys, curbs, crosswalks and lane
markings on streets, a few parked cars, plane trees and benches on green and white
areas, lampposts, a café terrace with tables.

<!-- @section anchor -->
{Anchor} is a FINISHED TILE OF THIS SAME MAP, already approved. It is the style
reference for everything except geometry: same ink, same line weight, same amount
of detail, same way of drawing roofs, trees, shutters, shopfronts, cars and paving.
Match it exactly — a reader must not be able to tell which tile was drawn first.
Take nothing else from it: its buildings and streets belong to another part of the
town, and yours come from {lines}.

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

<!-- @section types_dry -->
CLOSED LIST OF BUILDING TYPES. Every single building belongs to one of these two
types and to no other. There is no third type:
  TYPE A — plastered town house: plain rendered façade, no visible frame or
    coursing, a simple moulded string course between floors at most.
  TYPE B — stone mansion (hôtel particulier): ashlar façade with quoins at the
    corners, one round-arched carriage porch, slightly taller than its neighbours.

THERE IS NO WATER ANYWHERE IN THIS TILE. This part of the town stands well away
from the river: draw no river, no canal, no quay, no bridge, no arch over water,
no boat, no half-timbered house standing in water. The famous houses of the Agout
belong to another tile.

<!-- @section types_wet -->
CLOSED LIST OF BUILDING TYPES. Every single building belongs to one of these three
types and to no other. There is no fourth type:
  TYPE A — half-timbered house on the river: exposed timber frame, corner posts,
    one sill beam and one or two diagonal braces per façade, upper floor clearly
    overhanging on visible corbels, ground floor rising straight out of the water
    on stone footings. A building is TYPE A only where it actually stands on the
    blue of {sem}; nowhere else.
  TYPE B — plastered town house: plain rendered façade, no visible frame or
    coursing, a simple moulded string course between floors at most.
  TYPE C — stone mansion (hôtel particulier): ashlar façade with quoins at the
    corners, one round-arched carriage porch, slightly taller than its neighbours.

<!-- @section architecture_rules -->
RULES THAT APPLY TO EVERY BUILDING WITHOUT EXCEPTION:
  - two or three storeys, never more, never a single-storey shed;
  - the roof is pitched with a visible ridge, low slope, and a génoise cornice of
    two stacked tile courses under the eaves; no roof is flat, no roof is a
    terrace with a parapet. The tiles are SUGGESTED, never drawn one by one: two
    or three short courses along the eaves and nothing on the rest of the slope,
    which stays bare white paper. Never cover a roof with a grid or a scale
    pattern of tiles;
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
a word or a number, here or anywhere else in the image. The names above are given
to you so you know WHAT each shop sells — do not write any of them on the drawing.

This list tells you WHAT stands here. It never tells you WHERE, HOW BIG or HOW MANY:
those come from {lines} and from {lines} alone. Do not compose a square, a street or
a row of buildings of your own — trace the shapes that are in {lines}, at their size
and their angle, and put the listed things on them. A statue, a kiosk or market
stalls go only where {lines} shows something to draw them on. TREES are the one
exception: they are not drawn in {lines} at all, and you place them wherever {sem}
is green — one tree per green disc, a row of trees along a green strip.

<!-- @section water -->
In {sem}, blue marks water: the river Agout and its mill races. Draw water as calm
ripple lines between stone quays, never as a building or a street.

<!-- @section ref02 -->
{Ref02} is a second reference showing the ARCHITECTURE of Castres in this same ink
style: plastered façades with shutters, curved terracotta roofs, stone mansions, and
— in the part of it that shows the riverbank — half-timbered houses above the water.
Take the buildings from {ref02} and the ink style from {ref01}. Where {ref02} shows a
river, a quay or a bridge, that is a different part of the town: use it only if {sem}
shows blue in yours.

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

<!-- @section geometry_last -->
LAST AND ABOVE EVERYTHING ELSE. {Lines} is the ground truth. Every other image in
this message — the style reference, the neighbouring tiles — shows you HOW to draw,
never WHAT stands here or WHERE. Before you finish, check your drawing against
{lines}: every building of {lines} must be present, at its place, at its size, at
its angle; and no BUILDING may stand where {lines} shows none. An area left blank
in {lines} carries no building — only the paving, the greenery and the street life
that {sem} calls for.

Finally, the ink. Your output uses TWO TONES AND NO OTHER: black ink, white paper.
NO GREY. Not a grey road, not a grey roof, not a grey wall in shadow, not a grey
tint, not a wash, not a screen of dots. Every surface you might be tempted to shade
or fill — the roadway, the roof slopes, the paving, the water — stays PURE WHITE and
is defined by its black outline alone. Colour is forbidden the same way: no green
trees, no blue water, not one coloured pixel. Trees are black outlines on white,
water is black ripple lines on white, roads are black kerbs and markings on white.
If any grey or any colour from {sem} has found its way into your drawing, it is wrong.

And keep the paper EMPTY. This tile is one square of a large map that will be
printed small: a texture that looks delicate at full size turns into a grey smudge
when the map is reduced. So no roof covered in tiles, no wall covered in stones or
bricks, no ground covered in paving joints, no hatching, no stippling, no repeated
pattern filling any surface. Draw the outline, the openings, and two or three
courses of tile at the eaves — then stop. Far more than half of your paper is bare
white, and every large surface reads as white, not as texture. If your drawing is prettier than {lines} but does not match
it, it is wrong and must be redone.
