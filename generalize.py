"""Squelette de la carte : d'un extrait OSM a une poignee de VOLUMES.

    python3 generalize.py castres.osm blocks.geojson \\
      --bbox 43.603,2.235,43.610,2.246 \\
      --landmarks "Saint-Benoit,Eveche,Hotel de Ville,Goya"

Ni Blender ni reseau : shapely et numpy suffisent, et tout est testable seul.

CE QUE FAIT LA GENERALISATION, ET POURQUOI. Le vieux Castres compte plus de
deux mille emprises OSM. Dessinees une par une, elles donnent une dentelle :
la mesure faite sur la planche MicroMacro dit que la reference encre 15,7 % d'un
quartier dense avec des volumes LARGES et peu nombreux, la ou une carte fidele
encre 6,5 % en multipliant les petits contours. On ne gagne donc pas en ajoutant
du detail, mais en simplifiant la masse.

    emprises OSM -> ILOTS (ce que les rues delimitent) -> VOLUMES (ce qu'on dessine)

Objectif vise : entre 60 et 150 volumes sur toute la carte. Le script l'affiche
a chaque execution, c'est le seul chiffre a surveiller.

CE QUI N'EST PAS GENERALISE. Les reperes — eglises, batiments historiques, et
tout ce que --landmarks nomme — gardent leur emprise propre et ne sont jamais
fondus dans un ilot. Un joueur se repere sur eux ; les diluer reviendrait a
effacer la carte pour la simplifier.

TOUS LES REGLAGES se changent en ligne de commande, sans toucher au code :
`--set SHRINK=3.5 --set ROAD_EXTRA=3`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from shapely.affinity import rotate, translate
from shapely.geometry import LineString, MultiPolygon, Polygon, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent

REGLAGES = {
    # -- ce que le README documente ------------------------------------------
    "SHRINK": 2.5,           # m retires au pourtour d'un ilot = gagnes par la rue
    "ROAD_EXTRA": 1.5,       # m ajoutes a la largeur de toutes les voies
    "M2_PER_VOLUME": 450.0,  # m2 d'ilot par volume ; plus grand = moins de volumes
    "MAX_LEVELS": 3,         # plafond d'etages
    "SIMPLIFY": 2.5,         # m, tolerance de simplification des contours
    "GABLE_PROB": 0.6,       # part des petits volumes a toit a deux pans
    # -- le reste, reglable aussi --------------------------------------------
    "LEVEL_HEIGHT": 3.0,     # m par etage
    "DEFAULT_LEVELS": 2,     # quand OSM ne dit rien
    "GABLE_MAX_M2": 200.0,   # au-dela, un volume prend une croupe
    "GLUE": 1.5,             # m de dilatation pour souder les mitoyens en ilot
    "MIN_BUILDING_M2": 8.0,  # sous cette emprise, OSM decrit un mur ou un escalier
    "MIN_VOLUME_M2": 60.0,   # un volume plus petit ne se dessine pas a cette echelle
    "LEVEL_JITTER": 0.35,    # etages, +/- ; une ligne de toits plate se voit
    "RUE_MIN_LARGEUR": 5.0,  # m ; en dessous, la voie ne decoupe pas un ilot
    "COUR_MIN_M2": 400.0,    # une cour plus petite est comblee : l'ilot est une masse
    "LARGEUR_MIN": 6.0,      # m ; un ilot plus etroit que cela n'est pas un volume
}

# Largeur de chaussee par type de voie, en metres, AVANT ROAD_EXTRA. Ces valeurs
# ne sont pas dans OSM : elles viennent de l'usage francais courant.
LARGEUR_VOIE = {
    "motorway": 14.0, "trunk": 13.0, "primary": 12.0, "secondary": 10.0,
    "tertiary": 9.0, "unclassified": 7.0, "residential": 7.0,
    "living_street": 6.0, "service": 4.5, "pedestrian": 6.0,
    "footway": 3.0, "path": 2.5, "steps": 2.0, "cycleway": 2.5,
}


def sans_accent(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


def alea(*cle) -> float:
    """Tirage reproductible dans [0,1) : deux executions donnent la meme carte."""
    h = hashlib.blake2b(repr(cle).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2 ** 64


def latlon_vers_xy(lat, lon, lat0, lon0):
    """Projection equirectangulaire locale, la meme que tout le depot."""
    return ((lon - lon0) * 111320.0 * math.cos(math.radians(lat0)),
            (lat - lat0) * 110540.0)


# ------------------------------------------------------------------ lecture OSM
def lire_osm(chemin: Path, bbox):
    """Renvoie (batiments, voies, surfaces) en coordonnees metriques locales.

    Un element est garde des qu'UN de ses points touche la bbox : couper un
    batiment en deux au bord de la zone se voit plus qu'un batiment qui deborde.
    """
    lat0, lon0, lat1, lon1 = bbox
    olat, olon = (lat0 + lat1) / 2, (lon0 + lon1) / 2
    racine = ET.parse(chemin).getroot()
    noeuds = {n.get("id"): (float(n.get("lat")), float(n.get("lon")))
              for n in racine.iter("node")}

    def etiquettes(el):
        return {t.get("k"): t.get("v") for t in el.findall("tag")}

    def points(el):
        return [noeuds[nd.get("ref")] for nd in el.findall("nd")
                if nd.get("ref") in noeuds]

    def touche(pts):
        return any(lat0 <= la <= lat1 and lon0 <= lo <= lon1 for la, lo in pts)

    def en_metres(pts):
        return [latlon_vers_xy(la, lo, olat, olon) for la, lo in pts]

    batiments, voies, surfaces = [], [], []
    for w in racine.iter("way"):
        t = etiquettes(w)
        pts = points(w)
        if len(pts) < 2 or not touche(pts):
            continue
        xy = en_metres(pts)
        ferme = len(xy) >= 4 and xy[0] == xy[-1]

        if "building" in t or "building:part" in t:
            if not ferme:
                continue
            poly = Polygon(xy).buffer(0)
            if poly.is_empty or poly.area < REGLAGES["MIN_BUILDING_M2"]:
                continue
            batiments.append((poly, t, int(w.get("id"))))
        elif "highway" in t:
            voies.append((LineString(xy), t))
        elif ferme and ("natural" in t or "landuse" in t or "leisure" in t
                        or t.get("place") == "square" or "waterway" in t):
            poly = Polygon(xy).buffer(0)
            if not poly.is_empty:
                surfaces.append((poly, t))
    return batiments, voies, surfaces, (olat, olon)


# --------------------------------------------------------------- generalisation
def est_repere(tags: dict, noms) -> bool:
    """Un repere ne se fond jamais dans un ilot."""
    if tags.get("amenity") == "place_of_worship" or "historic" in tags:
        return True
    if tags.get("building") in ("church", "chapel", "cathedral", "civic"):
        return True
    nom = sans_accent(tags.get("name", ""))
    return bool(nom) and any(n and n in nom for n in noms)


def corridors(voies, min_largeur: float = 0.0) -> MultiPolygon:
    """Emprise reservee aux rues : chaque axe dilate de sa demi-largeur.

    `min_largeur` ecarte les voies trop etroites pour separer deux ilots. Un
    ilot MicroMacro est borde par des RUES, pas par des passages : en laissant
    les sentiers et les venelles de service decouper la masse, le vieux Castres
    sortait a 196 ilots pour une cible de 60 a 150, et aucun reglage d'aire ne
    pouvait rattraper cela — on ne fait pas moins de volumes que d'ilots.
    """
    bandes = []
    for ligne, t in voies:
        base = LARGEUR_VOIE.get(t.get("highway"), 6.0)
        if base < min_largeur:
            continue
        bandes.append(ligne.buffer((base + REGLAGES["ROAD_EXTRA"]) / 2.0,
                                   cap_style=2, join_style=2))
    return unary_union(bandes) if bandes else Polygon()


def combler(poly: Polygon, seuil: float) -> Polygon:
    """Bouche les cours d'un ilot en dessous d'un seuil.

    Les emprises OSM d'un centre ancien forment des ANNEAUX autour de courettes.
    Soudees puis reculees, elles donnaient des rubans creux en U et en L au lieu
    de pates de maisons : le premier rendu du squelette ne montrait presque que
    cela. Un ilot se lit en masse pleine ; seules les vraies cours — cloitres,
    jardins, cours d'honneur — meritent d'etre gardees.
    """
    trous = [ring for ring in poly.interiors
             if Polygon(ring).area >= seuil]
    return Polygon(poly.exterior, trous)


def polygones(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in geom.geoms if g.geom_type == "Polygon" and not g.is_empty]


def ilots(batiments, rues) -> list[Polygon]:
    """Souder les mitoyens, degager les rues, reculer le pourtour.

    L'ordre compte. Souder d'abord, sinon chaque maison reste seule ; degager
    les rues ensuite, sinon la soudure enjambe la chaussee et colle les deux
    cotes d'une ruelle ; reculer en dernier, pour que le retrait porte sur le
    contour reel de l'ilot et pas sur celui de chaque maison.
    """
    colle = REGLAGES["GLUE"]
    masse = unary_union([p.buffer(colle, join_style=2) for p in batiments])
    masse = masse.buffer(-colle, join_style=2)
    # COMBLER AVANT DE CREUSER. Une cour est un TROU ; une fois la chaussee
    # soustraite, la meme cour n'est plus qu'une encoche ouverte sur la rue, et
    # boucher les trous ne l'attrape plus. Dans cet ordre, la moitie des ilots
    # restaient des rubans en U.
    masse = unary_union([combler(p, REGLAGES["COUR_MIN_M2"])
                         for p in polygones(masse)])
    if not rues.is_empty:
        masse = masse.difference(rues)
    sortie = []
    for p in polygones(masse):
        recule = p.buffer(-REGLAGES["SHRINK"], join_style=2)
        for q in polygones(recule):
            q = q.simplify(REGLAGES["SIMPLIFY"], preserve_topology=True)
            if q.area < REGLAGES["MIN_VOLUME_M2"]:
                continue
            # une lame de 3 m de large et 90 m de long passe le test d'aire et
            # ne se dessine pas : on exige aussi une largeur
            if q.buffer(-REGLAGES["LARGEUR_MIN"] / 2, join_style=2).is_empty:
                continue
            sortie.append(q)
    return sortie


def couper_en_parts(poly: Polygon, n: int) -> list[Polygon]:
    """Decoupe un ilot en n volumes d'aires egales, en travers de son axe long.

    La coupe se fait a aire egale et non a pas egal : un ilot en L coupe a pas
    egal donne un volume minuscule et un volume enorme.
    """
    if n <= 1:
        return [poly]
    rect = poly.minimum_rotated_rectangle
    if rect.geom_type != "Polygon":
        return [poly]
    bord = list(rect.exterior.coords)[:4]
    cotes = [(math.dist(bord[i], bord[(i + 1) % 4]),
              math.atan2(bord[(i + 1) % 4][1] - bord[i][1],
                         bord[(i + 1) % 4][0] - bord[i][0])) for i in range(4)]
    _, angle = max(cotes)
    centre = poly.centroid
    droit = rotate(poly, -angle, origin=centre, use_radians=True)
    x0, y0, x1, y1 = droit.bounds
    total = droit.area
    parts, reste, gauche = [], droit, x0
    for k in range(1, n):
        cible = total * k / n
        a, b = gauche, x1
        for _ in range(40):                    # dichotomie sur la position
            m = (a + b) / 2
            aire = droit.intersection(
                Polygon([(x0 - 1, y0 - 1), (m, y0 - 1), (m, y1 + 1),
                         (x0 - 1, y1 + 1)])).area
            if aire < cible:
                a = m
            else:
                b = m
        coupe = (a + b) / 2
        bande = Polygon([(gauche - 1, y0 - 1), (coupe, y0 - 1),
                         (coupe, y1 + 1), (gauche - 1, y1 + 1)])
        for q in polygones(reste.intersection(bande)):
            parts.append(q)
        reste = reste.difference(bande)
        gauche = coupe
    parts += polygones(reste)
    return [rotate(p, angle, origin=centre, use_radians=True) for p in parts]


def niveaux_de(poly: Polygon, batiments) -> int:
    """Etages lus dans OSM sur les emprises couvertes, sinon le defaut."""
    lus = []
    for p, t, _ in batiments:
        if not p.intersects(poly):
            continue
        for cle in ("building:levels", "levels"):
            if cle in t:
                try:
                    lus.append(float(t[cle]))
                except ValueError:
                    pass
                break
    if not lus:
        return REGLAGES["DEFAULT_LEVELS"]
    lus.sort()
    return int(round(lus[len(lus) // 2]))


def volumes(blocs, batiments) -> list[dict]:
    sortie = []
    for i, bloc in enumerate(blocs):
        n = max(1, int(round(bloc.area / REGLAGES["M2_PER_VOLUME"])))
        for j, part in enumerate(couper_en_parts(bloc, n)):
            part = part.simplify(REGLAGES["SIMPLIFY"], preserve_topology=True)
            if part.is_empty or part.area < REGLAGES["MIN_VOLUME_M2"]:
                continue
            niv = min(REGLAGES["MAX_LEVELS"], max(1, niveaux_de(part, batiments)))
            # une ligne de toits parfaitement plate se voit : on la casse d'un
            # tiers d'etage, toujours le meme pour un volume donne
            secousse = (alea("niv", i, j) - 0.5) * 2 * REGLAGES["LEVEL_JITTER"]
            hauteur = (niv + secousse) * REGLAGES["LEVEL_HEIGHT"]
            petit = part.area < REGLAGES["GABLE_MAX_M2"]
            toit = ("gable" if petit and alea("toit", i, j) < REGLAGES["GABLE_PROB"]
                    else "hip")
            sortie.append({"geom": part, "kind": "volume", "levels": niv,
                           "height": round(hauteur, 2), "roof": toit,
                           "area": round(part.area, 1)})
    return sortie


def reperes(batiments, noms) -> list[dict]:
    sortie = []
    for poly, t, wid in batiments:
        if not est_repere(t, noms):
            continue
        p = poly.simplify(REGLAGES["SIMPLIFY"] / 2, preserve_topology=True)
        niv = max(2, niveaux_de(poly, batiments))
        sortie.append({"geom": p, "kind": "landmark", "levels": niv,
                       "height": round(niv * REGLAGES["LEVEL_HEIGHT"] * 1.4, 2),
                       "roof": "hip", "name": t.get("name", ""),
                       "osm": wid, "area": round(p.area, 1)})
    return sortie


def surfaces_utiles(surfaces) -> list[dict]:
    genres = []
    for poly, t in surfaces:
        if "waterway" in t or t.get("natural") == "water":
            genre = "water"
        elif t.get("leisure") in ("park", "garden") or t.get("landuse") in ("grass", "forest"):
            genre = "green"
        elif t.get("place") == "square" or t.get("highway") == "pedestrian":
            genre = "square"
        else:
            continue
        p = poly.simplify(REGLAGES["SIMPLIFY"], preserve_topology=True)
        if not p.is_empty and p.area > 20:
            genres.append({"geom": p, "kind": genre, "area": round(p.area, 1)})
    return genres


def ecrire(chemin: Path, morceaux, origine, compte):
    fc = {"type": "FeatureCollection",
          "metadata": {"origin_latlon": list(origine), "units": "m",
                       "reglages": REGLAGES, "counts": compte},
          "features": []}
    for m in morceaux:
        props = {k: v for k, v in m.items() if k != "geom"}
        fc["features"].append({"type": "Feature", "properties": props,
                               "geometry": mapping(m["geom"])})
    chemin.write_text(json.dumps(fc), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("osm", type=Path)
    p.add_argument("sortie", type=Path)
    p.add_argument("--bbox", required=True,
                   help="minlat,minlon,maxlat,maxlon")
    p.add_argument("--landmarks", default="",
                   help="noms cherches dans le tag name, separes par des virgules")
    p.add_argument("--set", action="append", default=[], metavar="CLE=VALEUR")
    args = p.parse_args()

    for reglage in args.set:
        cle, _, valeur = reglage.partition("=")
        if cle not in REGLAGES:
            sys.exit(f"reglage inconnu : {cle}. Connus : {', '.join(sorted(REGLAGES))}")
        REGLAGES[cle] = type(REGLAGES[cle])(float(valeur))

    bbox = tuple(float(v) for v in args.bbox.split(","))
    if len(bbox) != 4:
        sys.exit("--bbox attend minlat,minlon,maxlat,maxlon")
    noms = [sans_accent(n.strip()) for n in args.landmarks.split(",") if n.strip()]

    batiments, voies, surfaces, origine = lire_osm(args.osm, bbox)
    # CLIPPAGE. Un element est garde des qu'un seul de ses points touche la
    # zone, pour ne pas trancher une rangee mitoyenne ; mais une rue qui
    # traverse file alors a des centaines de metres. Sans cette coupe, le
    # cadrage passait de 780 a 1464 m et la carte se noyait dans du blanc.
    cadre = Polygon([latlon_vers_xy(la, lo, *origine) for la, lo in
                     ((bbox[0], bbox[1]), (bbox[0], bbox[3]),
                      (bbox[2], bbox[3]), (bbox[2], bbox[1]))])
    marques = reperes(batiments, noms)
    a_part = unary_union([m["geom"] for m in marques]) if marques else Polygon()
    ordinaires = [b for b in batiments
                  if a_part.is_empty or not b[0].intersects(a_part)]

    rues = corridors(voies, REGLAGES["RUE_MIN_LARGEUR"])
    blocs = ilots([b[0] for b in ordinaires], rues)
    vols = volumes(blocs, ordinaires)
    decor = surfaces_utiles(surfaces)

    garde = []
    for m in vols + marques + decor:
        g = m["geom"].intersection(cadre)
        for part in polygones(g):
            if part.area >= REGLAGES["MIN_VOLUME_M2"] / 3:
                garde.append(dict(m, geom=part, area=round(part.area, 1)))
    vols = [m for m in garde if m["kind"] == "volume"]
    marques = [m for m in garde if m["kind"] == "landmark"]
    decor = [m for m in garde if m["kind"] not in ("volume", "landmark")]

    compte = {"batiments": len(batiments), "ilots": len(blocs),
              "volumes": len(vols), "reperes": len(marques),
              "surfaces": len(decor)}
    ecrire(args.sortie, vols + marques + decor, origine, compte)

    print(f"{compte['batiments']} batiments -> {compte['ilots']} ilots "
          f"-> {compte['volumes']} volumes  (+ {compte['reperes']} reperes, "
          f"{compte['surfaces']} surfaces)")
    total = compte["volumes"] + compte["reperes"]
    juge = ("dans la cible" if 60 <= total <= 150 else
            "TROP : monter M2_PER_VOLUME" if total > 150 else
            "TROP PEU : baisser M2_PER_VOLUME")
    print(f"objectif MicroMacro 60-150 volumes : {total} -> {juge}")
    if vols:
        aires = sorted(v["area"] for v in vols)
        print(f"aire d'un volume : mediane {aires[len(aires) // 2]:.0f} m2, "
              f"min {aires[0]:.0f}, max {aires[-1]:.0f}")
    print(f"-> {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
