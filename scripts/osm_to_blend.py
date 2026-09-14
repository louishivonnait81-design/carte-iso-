"""Construit assets/castres.blend a partir d'un extrait OpenStreetMap (.osm XML).

    python scripts/osm_to_blend.py assets/castres.osm --out assets/castres.blend

Remplace l'import Blosm : les sources OSM sont inaccessibles depuis l'environnement
de rendu, l'extrait est donc telecharge dans un navigateur puis depose ici.

Produit une scene organisee en collections nommees comme iso_tiles.py les attend :
    buildings    meshes extrudes a leur hauteur (tags height / building:levels)
    streets      courbes POLY au sol, largeur par classe dans obj["road_width"]
    vegetation   surfaces plates + arbres isoles (icospheres basse resolution)
    water        surfaces plates legerement sous le sol
Les tags OSM sont recopies en proprietes personnalisees. L'origine de la scene
(scene["lat"], scene["lon"]) est le centre de l'emprise, comme chez Blosm.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import latlon_to_xy  # noqa: E402

# --------------------------------------------------------------------------
# Classement des elements OSM
# --------------------------------------------------------------------------

ROAD_WIDTH = {          # largeur de chaussee par classe, en metres
    "motorway": 12.0, "trunk": 10.0, "primary": 9.0, "secondary": 8.0, "tertiary": 7.0,
    "residential": 6.0, "unclassified": 5.5, "living_street": 5.0, "service": 4.0,
    "pedestrian": 5.0, "footway": 2.5, "path": 2.0, "steps": 2.5, "cycleway": 2.5,
    "track": 3.0, "primary_link": 7.0, "secondary_link": 6.0, "tertiary_link": 6.0,
}
LEVEL_HEIGHT = 3.2      # hauteur d'un niveau, en metres
# Hauteurs par type quand OSM ne donne ni height ni building:levels (le cas de
# 3 738 batiments sur 3 763 ici). Une cathedrale a 8 m, c'est une grange.
HEIGHT_BY_KIND = {
    "cathedral": 24.0, "church": 16.0, "chapel": 9.0, "temple": 12.0,
    "townhall": 13.0, "public": 12.0, "civic": 12.0, "government": 12.0,
    "school": 10.0, "university": 12.0, "hospital": 14.0, "hotel": 12.0,
    "apartments": 12.0, "commercial": 10.0, "retail": 8.0, "office": 12.0,
    "industrial": 7.0, "warehouse": 7.0, "house": 7.0, "detached": 7.0,
    "terrace": 8.0, "shed": 3.0, "garage": 3.0, "garages": 3.0, "hut": 3.0,
    "roof": 3.0, "kiosk": 3.0, "greenhouse": 3.0,
}
DEFAULT_LEVELS = 2.5    # vieux Castres : R+2 dominant, quelques R+1
ROOF_RISE = 8.0         # hauteur maximale de toiture au-dessus du dernier niveau

# Une emprise minuscule n'est pas un volume habitable : c'est une cage
# d'escalier, une courette, un appentis, ou l'epaisseur d'un mur saisie comme
# polygone. Extrudee a 12 m et coiffee d'une croupe, elle sort en pic. Mesure
# sur la grille : 5,5 % des "batiments" font moins de 4 m2, et 10 % ont un petit
# cote de moins de 2 m. Ils appartiennent de toute facon a la masse voisine,
# avec laquelle ils partagent leurs noeuds.
MIN_BUILDING_AREA = 4.0   # m2

# Une croupe a besoin de place. L'inset des versants vaut la moitie du petit
# cote ; sous ce seuil la face du dessus degenere et se replie sur elle-meme,
# ce qui produisait les diagonales que Freestyle dessinait ensuite fidelement.
MIN_HIP_SHORT_SIDE = 4.0  # m
WATER_Z = 0.01          # a plat, juste au-dessus du sol blanc pour rester visible
# Hauteur de bordure. Les surfaces pietonnes sont des dalles, pas des nappes :
# Freestyle ne sort aucun trait sur une nappe posee a plat, et le sol restait
# blanc — 47,6 % de la place Jean Jaures pour 0,79 % de trait. Une bordure de
# trottoir est une marche : en lui donnant son epaisseur reelle, la silhouette
# apparait d'elle-meme et l'on voit enfin ou s'arrete un batiment.
KERB_HEIGHT = 0.16
BRIDGE_Z = 1.0
TREE_RADIUS, TREE_HEIGHT = 3.0, 5.5

# Reperes ponctuels. OSM decrit la statue de Jean Jaures, la fontaine de la place
# ou les toilettes par un simple noeud ; osm_to_blend ne construisait de la
# geometrie que pour les chemins, si bien que leur position n'atteignait le
# modele que par une phrase — "en bas a droite", soit un neuvieme de tuile.
# Chaque repere recoit donc un volume simple mais physiquement plausible, a
# l'inverse des icospheres d'arbre qui ne ressemblaient a rien.
POINT_MARKERS = {
    ("historic", "memorial"): "plinth",
    ("historic", "monument"): "plinth",
    ("tourism", "artwork"): "plinth",
    ("amenity", "fountain"): "basin",
    ("amenity", "toilets"): "kiosk",
}
PLINTH = (1.5, 1.5, 2.2)      # socle : largeur, profondeur, hauteur
FIGURE = (0.55, 0.4, 1.8)     # la figure dessus
BASIN_RADIUS, BASIN_HEIGHT = 1.8, 0.8
KIOSK = (2.2, 2.2, 2.6)

# Voies sans voiture : ce sont des SOLS, pas des rues. Les classer en rue les
# faisait ressortir en gris fonce dans la passe semantique, et le modele y
# dessinait chaussee, passages pietons et voitures en travers d'une esplanade
# pietonne — c'est ce qui est arrive a la place Jean Jaures.
PEDESTRIAN_HIGHWAYS = {"pedestrian", "footway", "path", "steps", "corridor",
                       "platform", "track"}
# Surfaces explicitement pietonnes ou minerales : du sol ouvert, blanc.
OPEN_GROUND_TAGS = {("place", "square"), ("highway", "pedestrian"),
                    ("area:highway", "pedestrian"), ("man_made", "courtyard")}
# Bassins cartographies comme surfaces. La vasque de la statue de Jean Jaures est
# un polygone ferme de 8,3 x 7,5 m dans OSM, et La Fontaine des Angelots un autre
# de 8,9 m : category_of les ignorait tous les deux, aucun n'etait rendu.
BASIN_TAGS = {("amenity", "fountain")}
BASIN_RIM = 0.55        # hauteur de margelle

VEGETATION_TAGS = {
    ("leisure", "park"), ("leisure", "garden"), ("leisure", "pitch"),
    ("landuse", "grass"), ("landuse", "forest"), ("landuse", "village_green"),
    ("landuse", "cemetery"), ("landuse", "orchard"), ("landuse", "meadow"),
    ("natural", "wood"), ("natural", "scrub"), ("natural", "grassland"),
    ("natural", "heath"),
}
WATER_TAGS = {
    ("natural", "water"), ("waterway", "riverbank"), ("landuse", "reservoir"),
    ("landuse", "basin"),
}
STREET_AREA_TAGS = {("amenity", "parking"), ("landuse", "garages")}


def category_of(tags: dict) -> str | None:
    if "building" in tags or "building:part" in tags:
        return "building"
    if any((k, v) in WATER_TAGS for k, v in tags.items()) or "water" in tags:
        return "water"
    if any((k, v) in VEGETATION_TAGS for k, v in tags.items()):
        return "vegetation"
    if any((k, v) in BASIN_TAGS for k, v in tags.items()):
        return "basin"
    if any((k, v) in OPEN_GROUND_TAGS for k, v in tags.items()):
        return "open_ground"
    if any((k, v) in STREET_AREA_TAGS for k, v in tags.items()):
        return "street_area"
    if "highway" in tags:
        if tags["highway"] in PEDESTRIAN_HIGHWAYS:
            return "open_ground"
        return "street" if tags.get("area") != "yes" else "open_ground"
    return None


# Provenance et confiance de chaque hauteur. Sur Castres, 3 738 batiments sur
# 3 763 n'ont ni height ni building:levels : sans ce suivi, une hauteur devinee a
# partir du seul type de batiment est indiscernable d'une hauteur mesuree, et
# c'est le maillon le plus faible de la geometrie.
# Hauteur deduite de la FONCTION quand le tag building ne dit rien.
HEIGHT_BY_FUNCTION = {
    ("amenity", "place_of_worship"): 16.0, ("amenity", "townhall"): 13.0,
    ("amenity", "theatre"): 14.0, ("amenity", "courthouse"): 13.0,
    ("amenity", "hospital"): 14.0, ("amenity", "school"): 10.0,
    ("amenity", "college"): 12.0, ("amenity", "university"): 12.0,
    ("amenity", "library"): 11.0, ("amenity", "marketplace"): 9.0,
    ("amenity", "police"): 11.0, ("amenity", "fire_station"): 9.0,
    ("amenity", "prison"): 12.0, ("amenity", "cinema"): 12.0,
    ("tourism", "museum"): 12.0, ("tourism", "hotel"): 12.0,
    ("historic", "castle"): 20.0, ("historic", "tower"): 20.0,
    ("historic", "monument"): 12.0, ("man_made", "tower"): 20.0,
    ("man_made", "water_tower"): 25.0,
}

HEIGHT_CONFIDENCE = {
    "measured": 0.98,   # tag height, ou releve LiDAR fourni
    "levels": 0.90,     # building:levels x hauteur d'etage
    "kind": 0.55,       # deduite du type (eglise, immeuble, garage...)
    "default": 0.35,    # rien du tout : 2,5 niveaux
}


def building_height(tags: dict, measured: dict | None = None,
                    osm_id: int | None = None) -> tuple[float, str, float]:
    """Renvoie (hauteur, source, confiance).

    `measured` permet d'injecter des hauteurs relevees — LiDAR HD de l'IGN, BD
    TOPO, ou simple correction a la main — sous la forme {osm_id: hauteur}.
    """
    if measured and osm_id is not None and osm_id in measured:
        return float(measured[osm_id]), "measured", HEIGHT_CONFIDENCE["measured"]
    for key in ("height", "building:height"):
        if key in tags:
            try:
                return (float(str(tags[key]).replace("m", "").strip()),
                        "measured", HEIGHT_CONFIDENCE["measured"])
            except ValueError:
                pass
    kind = tags.get("building", "yes")
    if "building:levels" in tags:
        try:
            levels = float(tags["building:levels"])
            if kind in {"shed", "garage", "garages", "hut", "roof"}:
                levels = min(levels, 1.0)
            return levels * LEVEL_HEIGHT, "levels", HEIGHT_CONFIDENCE["levels"]
        except ValueError:
            pass
    if kind in HEIGHT_BY_KIND:
        return HEIGHT_BY_KIND[kind], "kind", HEIGHT_CONFIDENCE["kind"]
    # Beaucoup d'edifices publics sont tagues building=yes et ne se reconnaissent
    # qu'a leur fonction : l'eglise Saint-Jean-Saint-Louis se retrouvait a 8 m,
    # la hauteur d'une maison de ville.
    for key in ("amenity", "historic", "tourism", "man_made"):
        value = tags.get(key)
        if value and (key, value) in HEIGHT_BY_FUNCTION:
            return HEIGHT_BY_FUNCTION[(key, value)], "kind", HEIGHT_CONFIDENCE["kind"]
    return DEFAULT_LEVELS * LEVEL_HEIGHT, "default", HEIGHT_CONFIDENCE["default"]


# --------------------------------------------------------------------------
# Lecture du XML
# --------------------------------------------------------------------------

class Osm:
    def __init__(self) -> None:
        self.nodes: dict[int, tuple[float, float]] = {}
        self.node_tags: dict[int, dict] = {}
        self.ways: dict[int, list[int]] = {}
        self.way_tags: dict[int, dict] = {}
        self.relations: list[tuple[dict, list[tuple[str, int]]]] = []
        self.bounds: tuple[float, float, float, float] | None = None

    @classmethod
    def parse(cls, path: Path) -> "Osm":
        osm = cls()
        for _, el in ET.iterparse(path, events=("end",)):
            if el.tag == "bounds":
                osm.bounds = (float(el.get("minlat")), float(el.get("minlon")),
                              float(el.get("maxlat")), float(el.get("maxlon")))
            elif el.tag == "node":
                nid = int(el.get("id"))
                osm.nodes[nid] = (float(el.get("lat")), float(el.get("lon")))
                tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
                if tags:
                    osm.node_tags[nid] = tags
                el.clear()
            elif el.tag == "way":
                wid = int(el.get("id"))
                osm.ways[wid] = [int(n.get("ref")) for n in el.findall("nd")]
                osm.way_tags[wid] = {t.get("k"): t.get("v") for t in el.findall("tag")}
                el.clear()
            elif el.tag == "relation":
                tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
                members = [(m.get("role") or "outer", int(m.get("ref")))
                           for m in el.findall("member") if m.get("type") == "way"]
                if tags.get("type") == "multipolygon" and category_of(tags):
                    osm.relations.append((tags, members))
                el.clear()
        return osm

    def origin(self) -> tuple[float, float]:
        if self.bounds:
            return ((self.bounds[0] + self.bounds[2]) / 2, (self.bounds[1] + self.bounds[3]) / 2)
        lats = [p[0] for p in self.nodes.values()]
        lons = [p[1] for p in self.nodes.values()]
        return (sum(lats) / len(lats), sum(lons) / len(lons))


def assemble_rings(way_lists: list[list[int]]) -> list[list[int]]:
    """Recolle des chemins ouverts en anneaux fermes par leurs extremites."""
    pending = [list(w) for w in way_lists if len(w) >= 2]
    rings: list[list[int]] = []
    while pending:
        ring = pending.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, other in enumerate(pending):
                if other[0] == ring[-1]:
                    ring += other[1:]
                elif other[-1] == ring[-1]:
                    ring += other[::-1][1:]
                elif other[-1] == ring[0]:
                    ring = other[:-1] + ring
                elif other[0] == ring[0]:
                    ring = other[::-1][:-1] + ring
                else:
                    continue
                pending.pop(i)
                changed = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


# --------------------------------------------------------------------------
# Construction Blender
# --------------------------------------------------------------------------

def is_boxy(pts: list[tuple[float, float]], box_fit_2d, min_fill: float = 0.82,
            max_vertices: int = 8) -> bool:
    """Vrai si le polygone remplit presque son rectangle englobant oriente."""
    if len(pts) > max_vertices:
        return False
    angle = box_fit_2d(pts)
    c, s_ = math.cos(angle), math.sin(angle)
    xs = [x * c - y * s_ for x, y in pts]
    ys = [x * s_ + y * c for x, y in pts]
    box = (max(xs) - min(xs)) * (max(ys) - min(ys))
    return box > 0 and abs(ring_area(pts)) / box >= min_fill


def obb_short_side(pts: list[tuple[float, float]], box_fit_2d) -> float:
    """Petite dimension du rectangle englobant oriente d'un polygone."""
    angle = box_fit_2d(pts)
    c, s_ = math.cos(angle), math.sin(angle)
    xs = [x * c - y * s_ for x, y in pts]
    ys = [x * s_ + y * c for x, y in pts]
    return min(max(xs) - min(xs), max(ys) - min(ys))


def ring_area(pts: list[tuple[float, float]]) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


def build_scene(osm: Osm, out: Path, roof: str, max_trees: int,
                measured: dict | None = None) -> dict:
    import bpy            # doit preceder bmesh : le module pip l'initialise
    import bmesh
    from mathutils import Vector
    from mathutils.geometry import box_fit_2d, tessellate_polygon

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    lat0, lon0 = osm.origin()
    scene["lat"], scene["lon"] = lat0, lon0
    if osm.bounds:
        scene["osm_bbox"] = list(osm.bounds)
    scene.unit_settings.system = "METRIC"

    collections = {}
    for name in ("buildings", "streets", "vegetation", "water", "open_ground"):
        col = bpy.data.collections.new(name)
        scene.collection.children.link(col)
        collections[name] = col

    def xy(nid: int) -> tuple[float, float] | None:
        p = osm.nodes.get(nid)
        return latlon_to_xy(p[0], p[1], lat0, lon0) if p else None

    def ring_xy(refs: list[int]) -> list[tuple[float, float]]:
        pts = [q for q in (xy(n) for n in refs) if q is not None]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        # sans doublons consecutifs
        clean = [pts[0]] if pts else []
        for q in pts[1:]:
            if q != clean[-1]:
                clean.append(q)
        return clean

    def set_props(obj, tags: dict) -> None:
        for k, v in tags.items():
            if len(k) < 60:
                obj[k.replace(".", "_")] = v

    counts = defaultdict(int)
    provenance: dict[str, dict] = {}

    def record_height(key, obj, height, source, conf, tags) -> None:
        if obj is not None:
            obj["height_source"] = source
            obj["height_confidence"] = conf
        provenance[str(key)] = {
            "height_m": round(height, 2), "source": source, "confidence": conf,
            "name": tags.get("name"), "building": tags.get("building"),
        }

    def add_polygon(name: str, col, rings: list[list[tuple[float, float]]], z: float,
                    height: float, tags: dict, surface: str | None = None) -> None:
        rings = [r for r in rings if len(r) >= 3]
        if not rings:
            return None
        # anneau exterieur = le plus grand ; les autres sont des trous
        rings.sort(key=lambda r: -abs(ring_area(r)))
        outer, holes = rings[0], rings[1:]
        if ring_area(outer) < 0:
            outer = outer[::-1]
        holes = [h[::-1] if ring_area(h) > 0 else h for h in holes]

        bm = bmesh.new()
        loops = [outer] + holes
        verts_2d = [Vector((x, y, 0.0)) for ring in loops for x, y in ring]
        tris = tessellate_polygon([[Vector((x, y, 0.0)) for x, y in r] for r in loops])
        if not tris:
            bm.free()
            return None
        top_z = z + height
        top = [bm.verts.new((v.x, v.y, top_z)) for v in verts_2d]
        bm.verts.ensure_lookup_table()
        top_faces = []
        for tri in tris:
            try:
                top_faces.append(bm.faces.new([top[i] for i in tri]))
            except ValueError:
                pass
        if height > 0:
            bottom = [bm.verts.new((v.x, v.y, z)) for v in verts_2d]
            offset = 0
            for ring in loops:
                n = len(ring)
                for i in range(n):
                    a, b = offset + i, offset + (i + 1) % n
                    try:
                        bm.faces.new([bottom[a], bottom[b], top[b], top[a]])
                    except ValueError:
                        pass
                offset += n
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            # toiture : le dessus est rentre et surhausse -> lecture "toit a croupes"
            # Toit a croupes seulement si l'empreinte est quasi rectangulaire :
            # sur une empreinte OSM irreguliere, la rentree du dessus produit des
            # pointes et des quadrilateres gauches que Freestyle couvre de
            # diagonales. Une boite propre vaut mieux qu'un toit faux.
            if (roof == "hip" and top_faces and not holes and surface is None
                    and is_boxy(outer, box_fit_2d)
                    and obb_short_side(outer, box_fit_2d) >= MIN_HIP_SHORT_SIDE):
                bmesh.ops.dissolve_edges(bm, edges=[e for e in bm.edges
                                                    if all(f in top_faces for f in e.link_faces)
                                                    and len(e.link_faces) == 2],
                                         use_verts=False)
                tops = [f for f in bm.faces if all(abs(v.co.z - top_z) < 1e-6 for v in f.verts)]
                if tops:
                    # Un vrai toit a croupes : les versants se rejoignent sur un
                    # faite. L'inset doit donc valoir la moitie de la petite
                    # dimension du rectangle englobant oriente, a un cheveu pres
                    # pour ne pas degenerer la face de dessus.
                    short = obb_short_side(outer, box_fit_2d)
                    inset = 0.49 * short
                    rise = min(ROOF_RISE, 0.53 * inset)     # ~28 deg, pente des tuiles canal
                    bmesh.ops.inset_region(bm, faces=tops, thickness=inset, depth=rise,
                                           use_even_offset=True)
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(name, mesh)
        col.objects.link(obj)
        set_props(obj, tags)
        if surface:
            obj["surface"] = surface
        return obj

    def add_street(name: str, refs: list[int], tags: dict) -> None:
        """Ruban plat le long d'une voie. Le nom du collection cible decoule de
        la categorie : une voie pietonne va dans open_ground, pas dans streets."""
        pts = [q for q in (xy(n) for n in refs) if q is not None]
        if len(pts) < 2:
            return
        curve = bpy.data.curves.new(name, "CURVE")
        curve.dimensions = "3D"
        curve.twist_mode = "Z_UP"        # le ruban de rue reste a plat
        spline = curve.splines.new("POLY")
        spline.points.add(len(pts) - 1)
        z = BRIDGE_Z if tags.get("bridge") in {"yes", "viaduct"} else 0.0
        if name.startswith("ground."):
            z += KERB_HEIGHT          # une ruelle pietonne est au niveau du trottoir
        for p, (x, y) in zip(spline.points, pts):
            p.co = (x, y, z, 1.0)
        obj = bpy.data.objects.new(name, curve)
        target = "open_ground" if name.startswith("ground.") else "streets"
        collections[target].objects.link(obj)
        set_props(obj, tags)
        obj["road_width"] = ROAD_WIDTH.get(tags.get("highway", ""), 4.0)
        obj["surface"] = "open_ground" if target == "open_ground" else "street"

    # --- chemins fermes et ouverts ---
    used_in_relation = {ref for _, members in osm.relations for _, ref in members}
    for wid, refs in osm.ways.items():
        tags = osm.way_tags.get(wid, {})
        cat = category_of(tags)
        if cat is None or wid in used_in_relation and cat != "street":
            continue
        closed = len(refs) >= 4 and refs[0] == refs[-1]
        if cat == "street":
            add_street(f"street.{wid}", refs, tags)
            counts["streets"] += 1
        elif cat == "open_ground" and not closed:
            # ruelle ou traverse pietonne : un ruban de sol, pas une chaussee
            add_street(f"ground.{wid}", refs, tags)
            counts["open_ground"] += 1
        elif closed:
            ring = ring_xy(refs)
            if cat == "building":
                if abs(ring_area(ring)) < MIN_BUILDING_AREA:
                    counts["buildings_skipped"] += 1
                    continue
                height, source, conf = building_height(tags, measured, wid)
                obj = add_polygon(f"building.{wid}", collections["buildings"], [ring], 0.0,
                                  height, tags)
                record_height(wid, obj, height, source, conf, tags)
                counts["buildings"] += 1
            elif cat == "vegetation":
                add_polygon(f"vegetation.{wid}", collections["vegetation"], [ring], 0.02, 0.0, tags)
                counts["vegetation"] += 1
            elif cat == "water":
                add_polygon(f"water.{wid}", collections["water"], [ring], WATER_Z, 0.0, tags)
                counts["water"] += 1
            elif cat == "street_area":
                add_polygon(f"street.{wid}", collections["streets"], [ring], 0.01, 0.0,
                            tags, surface="street")
                counts["streets"] += 1
            elif cat == "open_ground":
                add_polygon(f"ground.{wid}", collections["open_ground"], [ring], 0.0,
                            KERB_HEIGHT, tags, surface="open_ground")
                counts["open_ground"] += 1
            elif cat == "basin":
                add_polygon(f"basin.{wid}", collections["open_ground"], [ring], 0.0,
                            BASIN_RIM, tags, surface="open_ground")
                counts["basins"] += 1

    # --- multipolygones (batiments a cour, rives de l'Agout, parcs) ---
    for tags, members in osm.relations:
        cat = category_of(tags)
        outers = assemble_rings([osm.ways[r] for role, r in members
                                 if role == "outer" and r in osm.ways])
        inners = assemble_rings([osm.ways[r] for role, r in members
                                 if role == "inner" and r in osm.ways])
        if not outers:
            continue
        inner_xy = [ring_xy(r) for r in inners]
        for i, outer in enumerate(outers):
            rings = [ring_xy(outer)] + inner_xy
            rid = f"rel.{abs(hash(tuple(outer))) % 10**9}.{i}"
            if cat == "building":
                height, source, conf = building_height(tags, measured)
                obj = add_polygon(f"building.{rid}", collections["buildings"], rings, 0.0,
                                  height, tags)
                record_height(rid, obj, height, source, conf, tags)
                counts["buildings"] += 1
            elif cat == "vegetation":
                add_polygon(f"vegetation.{rid}", collections["vegetation"], rings, 0.02, 0.0, tags)
                counts["vegetation"] += 1
            elif cat == "water":
                add_polygon(f"water.{rid}", collections["water"], rings, WATER_Z, 0.0, tags)
                counts["water"] += 1
            elif cat == "street_area":
                add_polygon(f"street.{rid}", collections["streets"], rings, 0.01, 0.0,
                            tags, surface="street")
                counts["streets"] += 1
            elif cat == "open_ground":
                add_polygon(f"ground.{rid}", collections["open_ground"], rings, 0.0,
                            KERB_HEIGHT, tags, surface="open_ground")
                counts["open_ground"] += 1

    # --- reperes ponctuels ---
    def marker_mesh(kind: str):
        bm = bmesh.new()
        if kind == "basin":
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8,
                                  radius1=BASIN_RADIUS, radius2=BASIN_RADIUS * 0.92,
                                  depth=BASIN_HEIGHT)
            bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, BASIN_HEIGHT / 2))
        else:
            box = KIOSK if kind == "kiosk" else PLINTH
            bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, verts=bm.verts, vec=box)
            bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, box[2] / 2))
            if kind == "plinth":
                top = bmesh.ops.create_cube(bm, size=1.0)["verts"]
                bmesh.ops.scale(bm, verts=top, vec=FIGURE)
                bmesh.ops.translate(bm, verts=top,
                                    vec=(0, 0, box[2] + FIGURE[2] / 2))
        mesh = bpy.data.meshes.new(f"marker_{kind}")
        bm.to_mesh(mesh)
        bm.free()
        return mesh

    meshes: dict[str, object] = {}
    for nid, tags in osm.node_tags.items():
        kind = next((v for k, v in POINT_MARKERS.items() if tags.get(k[0]) == k[1]), None)
        if kind is None:
            continue
        p = xy(nid)
        if p is None:
            continue
        if kind not in meshes:
            meshes[kind] = marker_mesh(kind)
        obj = bpy.data.objects.new(f"landmark.{nid}", meshes[kind])
        obj.location = (p[0], p[1], 0.0)
        collections["open_ground"].objects.link(obj)
        set_props(obj, tags)
        # sol blanc dans la passe semantique : un repere n'est pas un batiment,
        # et la regle "toute forme gris clair devient un batiment" ne doit pas
        # s'y appliquer. Sa silhouette suffit dans le dessin au trait.
        obj["surface"] = "open_ground"
        counts["landmarks"] += 1

    # --- arbres isoles ---
    trees = [nid for nid, tags in osm.node_tags.items() if tags.get("natural") == "tree"]
    if trees:
        proto_mesh = bpy.data.meshes.new("tree_canopy")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=3, radius=TREE_RADIUS)
        for f in bm.faces:
            f.smooth = True
        bm.to_mesh(proto_mesh)
        bm.free()
        for nid in trees[:max_trees]:
            p = xy(nid)
            if p is None:
                continue
            obj = bpy.data.objects.new(f"tree.{nid}", proto_mesh)
            obj.location = (p[0], p[1], TREE_HEIGHT)
            obj.scale = (1.0, 1.0, 0.7)
            collections["vegetation"].objects.link(obj)
            obj["natural"] = "tree"
            counts["trees"] += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    provenance_path = out.with_name(out.stem + "_confidence.json")
    provenance_path.write_text(json.dumps(
        {"heights": provenance,
         "legend": {k: f"confiance {v}" for k, v in HEIGHT_CONFIDENCE.items()}},
        indent=2, ensure_ascii=False), encoding="utf-8")
    counts["_provenance_path"] = str(provenance_path)
    return dict(counts)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("osm", type=Path, help="extrait OSM XML (.osm)")
    p.add_argument("--out", type=Path, default=Path("assets/castres.blend"))
    p.add_argument("--roof", choices=["hip", "flat"], default="hip",
                   help="toiture suggeree sur les batiments")
    p.add_argument("--max-trees", type=int, default=400)
    p.add_argument("--heights", type=Path, default=None,
                   help="JSON {osm_id: hauteur_m} de hauteurs relevees (LiDAR HD, "
                        "BD TOPO, ou corrections a la main) : elles priment sur tout")
    args = p.parse_args()

    if not args.osm.exists():
        sys.exit(f"Extrait introuvable : {args.osm}")
    osm = Osm.parse(args.osm)
    lat0, lon0 = osm.origin()
    print(f"[osm] {len(osm.nodes)} noeuds, {len(osm.ways)} chemins, "
          f"{len(osm.relations)} multipolygones utiles")
    print(f"[osm] origine scene : lat {lat0:.6f} lon {lon0:.6f}"
          + (f"  emprise {osm.bounds}" if osm.bounds else ""))

    measured = None
    if args.heights:
        measured = {int(k): float(v) for k, v in
                    json.loads(args.heights.read_text(encoding="utf-8")).items()}
        print(f"[osm] {len(measured)} hauteurs relevees chargees depuis {args.heights}")
    counts = build_scene(osm, args.out, args.roof, args.max_trees, measured)
    provenance_path = counts.pop("_provenance_path", None)
    for k, v in sorted(counts.items()):
        print(f"[osm] {k:<11}: {v}")
    if provenance_path:
        prov = json.loads(Path(provenance_path).read_text(encoding="utf-8"))["heights"]
        from collections import Counter
        tally = Counter(e["source"] for e in prov.values())
        total = sum(tally.values()) or 1
        print("[osm] provenance des hauteurs :")
        for src in ("measured", "levels", "kind", "default"):
            n = tally.get(src, 0)
            print(f"[osm]   {src:<9} {n:5d}  {n/total*100:5.1f} %  "
                  f"(confiance {HEIGHT_CONFIDENCE[src]})")
        print(f"[osm] provenance ecrite : {provenance_path}")
    print(f"[osm] scene ecrite : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
