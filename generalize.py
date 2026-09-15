#!/usr/bin/env python3
"""
generalize.py — Étape 1 du pipeline MicroMacro-Castres.

Lit un fichier .osm (export OpenStreetMap / Blosm), généralise la ville
« façon MicroMacro » et écrit un GeoJSON en mètres (repère local) que
build_blender.py transforme en scène 3D.

Ce que fait le script, dans l'ordre :
  1. parse les bâtiments, routes, eau, parcs, arbres du .osm
  2. projette en mètres autour du centre de la zone
  3. repère les monuments (église, mairie, tags historic, ou noms donnés)
  4. fusionne les bâtiments contigus en îlots
  5. découpe chaque îlot en 1 à 4 volumes simples
  6. simplifie / redresse les contours
  7. rétrécit chaque volume (= élargit toutes les rues d'un coup)
  8. attribue hauteur plafonnée, type de toit, motif de façade
  9. construit les rubans de rues (trottoirs), eau, parcs, arbres

Usage :
  python3 generalize.py castres.osm blocks.geojson
  python3 generalize.py castres.osm blocks.geojson --bbox 43.603,2.235,43.610,2.246
  python3 generalize.py castres.osm blocks.geojson --landmarks "Saint-Benoît,Évêché,Hôtel de Ville"

Dépendances : pip install shapely numpy
"""

import argparse
import json
import math
import random
import sys
import xml.etree.ElementTree as ET

from shapely.geometry import (
    Polygon, MultiPolygon, LineString, Point, box, mapping
)
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

# ---------------------------------------------------------------------------
# Paramètres de généralisation — c'est ici qu'on règle le « look » MicroMacro
# ---------------------------------------------------------------------------
P = dict(
    SEED=42,
    MERGE_GAP=0.6,        # m : deux bâtiments à moins de ça sont fusionnés
    M2_PER_VOLUME=450.0,  # m² d'îlot par volume (→ 1 à 4 volumes par îlot)
    MAX_VOLUMES=4,
    SIMPLIFY=2.5,         # m : tolérance de simplification des contours
    RECT_MAX_VERTS=7,     # en dessous de ce nb de sommets → rectangle englobant
    SHRINK=2.5,           # m : recul de chaque volume (élargit les rues)
    MIN_AREA=40.0,        # m² : on jette les volumes plus petits
    LEVEL_H=3.2,          # m par niveau
    MAX_LEVELS=3,
    GABLE_MAX_AREA=220.0, # m² : petits volumes rectangulaires → toit à 2 pans
    GABLE_PROB=0.6,
    LANDMARK_DEFAULT_H=15.0,
    LANDMARK_MAX_H=22.0,
    LANDMARK_SIMPLIFY=1.2,
    LANDMARK_SHRINK=0.8,
    SIDEWALK=1.8,         # m : largeur du trottoir (2e trait de la rue)
    ROAD_EXTRA=1.5,       # m ajoutés à toutes les largeurs de rue
    TREE_SPACING=9.0,     # m : grille d'arbres dans les parcs
    TREE_JITTER=2.0,
)

ROAD_WIDTH = {          # largeurs de base par type OSM (m)
    "primary": 12, "primary_link": 10,
    "secondary": 10, "secondary_link": 8,
    "tertiary": 8, "tertiary_link": 7,
    "residential": 6, "unclassified": 6, "living_street": 5,
    "pedestrian": 6, "service": 4, "footway": 3, "path": 2.5, "steps": 2.5,
}
SKIP_ROADS = {"motorway", "trunk", "cycleway", "bridleway", "track", "corridor", "proposed", "construction"}

LANDMARK_BUILDING = {"church", "cathedral", "chapel", "basilica", "synagogue", "mosque",
                     "townhall", "castle", "palace", "museum", "temple"}
LANDMARK_AMENITY = {"place_of_worship", "townhall", "courthouse", "theatre", "library"}

MOTIFS = ["carre", "carre", "haute", "haute", "vitrine", "arcade"]


# ---------------------------------------------------------------------------
# 1. Lecture du .osm
# ---------------------------------------------------------------------------
def parse_osm(path):
    tree = ET.parse(path)
    root = tree.getroot()
    nodes, ways, rels = {}, {}, []
    for el in root:
        if el.tag == "node":
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            nodes[el.get("id")] = (float(el.get("lon")), float(el.get("lat")), tags)
        elif el.tag == "way":
            refs = [nd.get("ref") for nd in el.findall("nd")]
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            ways[el.get("id")] = (refs, tags)
        elif el.tag == "relation":
            members = [(m.get("type"), m.get("ref"), m.get("role")) for m in el.findall("member")]
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            rels.append((members, tags))
    return nodes, ways, rels


class Proj:
    """Projection équirectangulaire locale : suffisant à l'échelle d'un centre-ville."""
    def __init__(self, lon0, lat0):
        self.lon0, self.lat0 = lon0, lat0
        self.kx = 111320.0 * math.cos(math.radians(lat0))
        self.ky = 110540.0

    def __call__(self, lon, lat):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)


def way_coords(refs, nodes, proj):
    pts = []
    for r in refs:
        if r in nodes:
            lon, lat, _ = nodes[r]
            pts.append(proj(lon, lat))
    return pts


def is_closed(refs):
    return len(refs) >= 4 and refs[0] == refs[-1]


def poly_from_rings(outer, inners=()):
    try:
        p = Polygon(outer, [i for i in inners if len(i) >= 4])
        if not p.is_valid:
            p = p.buffer(0)
        return p if not p.is_empty else None
    except Exception:
        return None


def parse_height(tags):
    h = tags.get("height")
    if h:
        try:
            return float(str(h).lower().replace("m", "").strip())
        except ValueError:
            pass
    lv = tags.get("building:levels")
    if lv:
        try:
            return float(lv) * P["LEVEL_H"]
        except ValueError:
            pass
    return None


def is_landmark(tags, names):
    if tags.get("building") in LANDMARK_BUILDING:
        return True
    if tags.get("amenity") in LANDMARK_AMENITY:
        return True
    if "historic" in tags or "heritage" in tags:
        return True
    name = (tags.get("name") or "").lower()
    return any(n and n.lower() in name for n in names)


def collect(nodes, ways, rels, proj, names):
    buildings, roads, water, parks, trees = [], [], [], [], []
    used_in_rel = set()

    # Relations multipolygones (églises, grands bâtiments, plans d'eau)
    for members, tags in rels:
        if tags.get("type") != "multipolygon":
            continue
        outers, inners = [], []
        for mtype, ref, role in members:
            if mtype != "way" or ref not in ways:
                continue
            refs, _ = ways[ref]
            if not is_closed(refs):
                continue
            pts = way_coords(refs, nodes, proj)
            (outers if role != "inner" else inners).append(pts)
            used_in_rel.add(ref)
        for o in outers:
            p = poly_from_rings(o, inners)
            if p is None:
                continue
            if "building" in tags:
                buildings.append((p, tags))
            elif tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
                water.append(p)
            elif tags.get("leisure") in ("park", "garden") or tags.get("landuse") in ("grass", "village_green"):
                parks.append(p)

    for wid, (refs, tags) in ways.items():
        if wid in used_in_rel:
            continue
        pts = way_coords(refs, nodes, proj)
        if len(pts) < 2:
            continue
        if "building" in tags and is_closed(refs):
            p = poly_from_rings(pts)
            if p is not None:
                buildings.append((p, tags))
        elif "highway" in tags and tags["highway"] not in SKIP_ROADS:
            if tags.get("area") == "yes" and is_closed(refs):
                continue  # les places piétonnes : traitées comme espace libre
            roads.append((LineString(pts), tags["highway"]))
        elif (tags.get("natural") == "water" or tags.get("waterway") == "riverbank") and is_closed(refs):
            p = poly_from_rings(pts)
            if p is not None:
                water.append(p)
        elif (tags.get("leisure") in ("park", "garden") or tags.get("landuse") in ("grass", "village_green")) and is_closed(refs):
            p = poly_from_rings(pts)
            if p is not None:
                parks.append(p)

    for nid, (lon, lat, tags) in nodes.items():
        if tags.get("natural") == "tree":
            trees.append(Point(proj(lon, lat)))

    return buildings, roads, water, parks, trees


# ---------------------------------------------------------------------------
# 2. Généralisation
# ---------------------------------------------------------------------------
def explode(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if hasattr(geom, "geoms"):
        return [g for g in geom.geoms if isinstance(g, Polygon)]
    return []


def orthogonalize(poly):
    """Contours simples et droits : petits polygones → rectangle englobant."""
    s = poly.simplify(P["SIMPLIFY"], preserve_topology=True)
    if s.is_empty or not isinstance(s, Polygon):
        return None
    nverts = len(s.exterior.coords) - 1
    if nverts <= P["RECT_MAX_VERTS"]:
        r = s.minimum_rotated_rectangle
        # on ne remplace par le rectangle que s'il ne gonfle pas trop
        if r.area <= s.area * 1.45:
            return r
    return s


def shrink(poly, d):
    """Recul vers l'intérieur ; si le volume disparaît, on le réduit par homothétie."""
    e = poly.buffer(-d, join_style="mitre", mitre_limit=2.0)
    parts = [p for p in explode(e) if p.area >= P["MIN_AREA"]]
    if parts:
        return max(parts, key=lambda p: p.area)
    from shapely import affinity
    s = affinity.scale(poly, 0.65, 0.65, origin="centroid")
    return s if s.area >= P["MIN_AREA"] else None


def split_block(block, members):
    """Découpe un îlot en 1..MAX_VOLUMES volumes autour des plus gros bâtiments."""
    k = max(1, min(P["MAX_VOLUMES"], int(round(block.area / P["M2_PER_VOLUME"]))))
    members = sorted(members, key=lambda b: b.area, reverse=True)
    if k == 1 or len(members) <= 1:
        return [block]
    seeds = members[:k]
    groups = [[s] for s in seeds]
    for b in members[k:]:
        c = b.centroid
        i = min(range(k), key=lambda j: seeds[j].distance(c))
        groups[i].append(b)
    out = []
    g_ = P["MERGE_GAP"]
    for g in groups:
        u = unary_union([b.buffer(g_, join_style="mitre") for b in g]).buffer(-g_, join_style="mitre")
        out.extend(explode(u))
    return out


def generalize_buildings(buildings, names, rng):
    landmarks, ordinary = [], []
    for p, tags in buildings:
        (landmarks if is_landmark(tags, names) else ordinary).append((p, tags))

    features = []

    # --- monuments : contour fidèle, hauteur réelle plafonnée, pas de fenêtres
    for p, tags in landmarks:
        s = p.simplify(P["LANDMARK_SIMPLIFY"], preserve_topology=True).buffer(-P["LANDMARK_SHRINK"], join_style="mitre")
        for part in explode(s):
            h = parse_height(tags) or P["LANDMARK_DEFAULT_H"]
            h = min(h, P["LANDMARK_MAX_H"])
            features.append(feature(part, kind="landmark", height=round(h, 1), roof="plat",
                                    motif="none", name=tags.get("name", "")))

    # --- bâtiments ordinaires : îlots → volumes
    g_ = P["MERGE_GAP"]
    polys = [p for p, _ in ordinary]
    blocks = explode(unary_union([p.buffer(g_, join_style="mitre") for p in polys]).buffer(-g_, join_style="mitre"))
    print(f"  {len(polys)} bâtiments ordinaires → {len(blocks)} îlots", file=sys.stderr)

    n_vol = 0
    for block in blocks:
        members = [p for p in polys if p.intersects(block)]
        for vol in split_block(block, members):
            o = orthogonalize(vol)
            if o is None:
                continue
            s = shrink(o, P["SHRINK"])
            if s is None:
                continue
            s = orient(s, sign=1.0)  # anti-horaire
            # hauteur : niveaux des bâtiments d'origine si connus, sinon 2-3
            src_levels = [parse_height(t) for p, t in ordinary if p.intersects(s)]
            src_levels = [int(round(h / P["LEVEL_H"])) for h in src_levels if h]
            levels = max(src_levels) if src_levels else rng.choice([2, 2, 3, 3, 3])
            levels = max(1, min(P["MAX_LEVELS"], levels))
            nverts = len(s.exterior.coords) - 1
            gable = (nverts == 4 and s.area <= P["GABLE_MAX_AREA"] and rng.random() < P["GABLE_PROB"])
            features.append(feature(s, kind="volume", levels=levels,
                                    height=round(levels * P["LEVEL_H"], 2),
                                    roof="pignon" if gable else "plat",
                                    motif=rng.choice(MOTIFS)))
            n_vol += 1
    print(f"  → {n_vol} volumes, {len(landmarks)} monuments", file=sys.stderr)
    return features


def generalize_roads(roads, clip):
    ribbons = []
    for line, kind in roads:
        w = ROAD_WIDTH.get(kind, 5) + P["ROAD_EXTRA"]
        ribbons.append(line.buffer(w / 2.0, cap_style="flat", join_style="round"))
    if not ribbons:
        return [], []
    outer = unary_union(ribbons)
    if clip is not None:
        outer = outer.intersection(clip)
    inner = outer.buffer(-P["SIDEWALK"], join_style="round")
    return explode(outer), explode(inner)


def trees_from_parks(parks, existing, rng):
    pts = list(existing)
    sp, jit = P["TREE_SPACING"], P["TREE_JITTER"]
    for park in parks:
        minx, miny, maxx, maxy = park.bounds
        inset = park.buffer(-3.0)
        if inset.is_empty:
            continue
        y = miny + sp / 2
        while y < maxy:
            x = minx + sp / 2
            while x < maxx:
                pt = Point(x + rng.uniform(-jit, jit), y + rng.uniform(-jit, jit))
                if inset.contains(pt) and all(pt.distance(q) > 4.0 for q in pts[-50:]):
                    pts.append(pt)
                x += sp
            y += sp
    return pts


# ---------------------------------------------------------------------------
# 3. Sortie
# ---------------------------------------------------------------------------
def feature(geom, **props):
    return {"type": "Feature", "properties": props, "geometry": mapping(geom)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("osm")
    ap.add_argument("out")
    ap.add_argument("--bbox", help="minlat,minlon,maxlat,maxlon (WGS84)")
    ap.add_argument("--landmarks", default="", help="noms de monuments séparés par des virgules")
    ap.add_argument("--set", action="append", default=[], help="surcharge un paramètre, ex. --set SHRINK=3.5")
    a = ap.parse_args()

    for s in a.set:
        k, v = s.split("=", 1)
        P[k] = type(P[k])(v)
    rng = random.Random(P["SEED"])
    names = [n.strip() for n in a.landmarks.split(",") if n.strip()]

    print("Lecture du .osm…", file=sys.stderr)
    nodes, ways, rels = parse_osm(a.osm)
    lons = [n[0] for n in nodes.values()]
    lats = [n[1] for n in nodes.values()]
    if a.bbox:
        minlat, minlon, maxlat, maxlon = map(float, a.bbox.split(","))
    else:
        minlon, maxlon, minlat, maxlat = min(lons), max(lons), min(lats), max(lats)
    proj = Proj((minlon + maxlon) / 2, (minlat + maxlat) / 2)
    x0, y0 = proj(minlon, minlat)
    x1, y1 = proj(maxlon, maxlat)
    clip = box(x0, y0, x1, y1)

    buildings, roads, water, parks, trees = collect(nodes, ways, rels, proj, names)
    buildings = [(p, t) for p, t in buildings if p.intersects(clip)]
    roads = [(l.intersection(clip), k) for l, k in roads if l.intersects(clip)]
    roads = [(l, k) for l, k in roads if isinstance(l, LineString) and not l.is_empty]
    water = [w.intersection(clip) for w in water if w.intersects(clip)]
    parks = [p.intersection(clip) for p in parks if p.intersects(clip)]
    trees = [t for t in trees if clip.contains(t)]
    print(f"  périmètre {x1 - x0:.0f} × {y1 - y0:.0f} m ; {len(buildings)} bâtiments, "
          f"{len(roads)} tronçons, {len(water)} eau, {len(parks)} parcs, {len(trees)} arbres", file=sys.stderr)

    print("Généralisation…", file=sys.stderr)
    feats = generalize_buildings(buildings, names, rng)

    outer, inner = generalize_roads(roads, clip)
    feats += [feature(g, kind="road") for g in outer]
    feats += [feature(g, kind="sidewalk_inner") for g in inner]
    for w in water:
        feats += [feature(g, kind="water") for g in explode(w)]
    for p in parks:
        feats += [feature(g, kind="park") for g in explode(p)]
    all_trees = trees_from_parks([g for p in parks for g in explode(p)], trees, rng)
    feats += [feature(t, kind="tree", radius=round(rng.uniform(2.4, 3.4), 2)) for t in all_trees]

    out = {
        "type": "FeatureCollection",
        "crs_note": "coordonnées locales en mètres, origine = centre du périmètre",
        "bounds": [x0, y0, x1, y1],
        "params": P,
        "features": feats,
    }
    with open(a.out, "w") as f:
        json.dump(out, f)
    print(f"Écrit {a.out} : {len(feats)} entités", file=sys.stderr)


if __name__ == "__main__":
    main()
