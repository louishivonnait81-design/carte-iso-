"""Etape 11 — ouvrir le toit de quelques lieux, pour qu'on voie dedans.

    blender -b -P v2/11_ouvertures.py
    blender -b -P v2/11_ouvertures.py -- --choisir     # refaire la selection

Lit castres_pave.blend, ecrit castres_ouvert.blend.

PAS TOUS LES TOITS. Une carte dont chaque maison est ouverte n'est plus une
ville, c'est un plan de niveau. Dix lieux sont ouverts, pas un de plus : ceux ou
il se passe quelque chose. La liste vit dans config.json et s'edite a la main —
c'est un choix editorial, et il doit se voir comme tel.

COMMENT ELLE A ETE FAITE. `--choisir` la refabrique depuis OpenStreetMap :
chaque batiment recoit le poids du commerce qu'il contient (une boite de nuit,
un bar, un cafe, une boulangerie comptent plus qu'une agence immobiliere)
multiplie par la racine de son emprise, et l'on descend ce classement en
gardant 35 m entre deux lieux ouverts pour qu'ils ne se regroupent pas dans un
coin. 100 POI d'interieur, 48 batiments en contiennent au moins un : la selection
part donc d'un cinquieme du bati, pas du bati entier.

ON NE RETIRE QUE LE VERSANT QUI REGARDE LA CAMERA. Le faitage et le versant du
fond restent en place : la ligne de toits de la rue n'est pas trouee, et la
maison se lit toujours comme une maison. Le prix est mesure plus bas — le
versant qui reste mange une part de la piece.

LE PLANCHER. Une fois le versant retire, on voit le sol de la zone a travers les
murs : la maison devient une coquille vide posee sur la rue. On pose donc un
plancher a la hauteur de l'egout du toit, copie de l'emprise du batiment. C'est
la piece haute que l'on decouvre, pas la boutique du rez-de-chaussee — a 7 m de
hauteur moyenne il y a deux niveaux, et c'est le second que le toit couvrait.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

V2 = Path(__file__).resolve().parent
ROOT = V2.parent
CONFIG = V2 / "config.json"

# Un versant de toiture : ni plat (le plancher, les acroteres), ni vertical
# (les murs). La croupe de l'etape 6 monte a 0,88 en z, le faitage un peu plus.
PENTE_MIN, PENTE_MAX = 0.20, 0.985
FACE_CAMERA_MIN = 0.15   # produit scalaire minimal pour dire "ce pan nous fait face"
JEU_PLANCHER = 0.04      # m, pour ne pas coincider avec l'egout
EPAISSEUR_MUR = 0.35     # m, l'epaisseur de mur que montre la coupe
PAS_CLOISON = 4.5        # m, distance entre deux refends
HAUTEUR_CLOISON = 1.0    # m ; une cloison coupee, pas un mur entier


def direction_camera(rotation_z_deg: float) -> Vector:
    """Direction horizontale, dans la scene, qui pointe VERS la camera.

    A Z=315 la camera est au sud-ouest : un pan de toit nous fait face si sa
    normale a une composante dans cette direction.
    """
    a = math.radians(rotation_z_deg)
    return Vector((math.sin(a), -math.cos(a))).normalized()


def faces_du_bas(bm, zmin: float):
    """Faces horizontales du niveau du sol, quel que soit le sens de leur normale.

    Le sens ne se presume pas : plusieurs prismes sortent de l'import sans fond
    du tout, et le batiment 83181551 n'avait AUCUNE face sous 0,6 m — dix
    sommets au sol, neuf aretes, pas un seul polygone. On le referme avant de
    copier son emprise.
    """
    faces = [f for f in bm.faces
             if abs(f.normal.z) > 0.9 and f.calc_center_median().z < zmin + 0.6]
    if faces:
        return faces
    anneau = [e for e in bm.edges if all(v.co.z < zmin + 0.05 for v in e.verts)]
    if not anneau:
        return []
    cree = bmesh.ops.contextual_create(bm, geom=anneau)
    return [f for f in cree["faces"] if f.is_valid]


def epaissir_les_murs(bm, plancher) -> None:
    """Creuse le plancher de l'epaisseur d'un mur, sur son pourtour.

    Sans cela un toit retire ne se voit pas. Le premier rendu l'a montre sans
    appel : la piece etait une surface blanche au niveau de l'egout, bordee d'un
    seul trait — exactement ce que dessine un toit-terrasse. Un mur de pierre a
    une epaisseur ; la montrer donne le DOUBLE TRAIT qui dit que le toit a ete
    coupe, et non pose a plat.
    """
    resultat = bmesh.ops.inset_region(bm, faces=plancher, thickness=EPAISSEUR_MUR,
                                      depth=0.0, use_even_offset=False,
                                      use_boundary=True)
    bande = set(resultat["faces"])
    piece = [f for f in plancher if f.is_valid and f not in bande]
    verts = {v for f in piece for v in f.verts}
    if verts:
        bmesh.ops.translate(bm, verts=list(verts), vec=(0, 0, -EPAISSEUR_MUR))


def axe_principal(points) -> Vector:
    """Direction dominante d'un nuage de points, par analyse en composantes."""
    n = len(points)
    mx = sum(p.x for p in points) / n
    my = sum(p.y for p in points) / n
    cxx = sum((p.x - mx) ** 2 for p in points) / n
    cyy = sum((p.y - my) ** 2 for p in points) / n
    cxy = sum((p.x - mx) * (p.y - my) for p in points) / n
    a = 0.5 * math.atan2(2 * cxy, cxx - cyy)
    return Vector((math.cos(a), math.sin(a), 0.0))


def dans_le_decouvert(point, triangles) -> bool:
    x, y = point.x, point.y
    for (ax, ay), (bx, by), (cx, cy) in triangles:
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
        v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
        if u >= -1e-6 and v >= -1e-6 and u + v <= 1 + 1e-6:
            return True
    return False


def bord_du_decouvert(pts, travers, decouvert):
    """Position, le long de `travers`, de la limite entre couvert et decouvert.

    Renvoie None si le decouvert occupe toute la piece : il n'y a alors rien a
    separer.
    """
    if not decouvert:
        return None
    vus = [x * travers.x + y * travers.y
           for t in decouvert for (x, y) in t]
    tous = [p.dot(travers) for p in pts]
    if max(vus) < max(tous) - 0.5:
        return max(vus)
    if min(vus) > min(tous) + 0.5:
        return min(vus)
    return None


def poser_cloisons(bm, z_piece: float, decouvert) -> int:
    """Refends dans la piece decouverte, tous les 4,5 m.

    Une piece vide ne se lit pas : le premier rendu montrait un grand plan blanc
    borde d'un trait, c'est-a-dire un toit-terrasse. Ce qui dit "interieur",
    avant tout meuble, c'est le CLOISONNEMENT — et il est vrai : aucune maison de
    ville n'a un plateau libre de quinze metres.

    Les cloisons ne sont pas des boites posees dessus : on coupe le plancher par
    un plan, puis on extrude les aretes nees de la coupe. Elles epousent donc
    exactement la piece, y compris quand elle est en L.

    Deux precautions, l'une de dessin, l'autre de justesse :
      * les refends suivent l'axe PROPRE du batiment, pas les axes du monde. Une
        grille en X et Y sur une maison posee de biais donnait un damier, qui
        se lit comme un entrepot et pas comme des pieces ;
      * une cloison n'est montee que sous la partie DECOUVERTE. Le versant
        conserve descend jusqu'a l'egout : partout ailleurs, une cloison d'un
        metre le traversait et semait des traits en travers de la toiture.
    """
    def piece_courante():
        return [f for f in bm.faces if f.normal.z > 0.9
                and abs(f.calc_center_median().z - z_piece) < 0.02]

    faces = piece_courante()
    if not faces:
        return 0
    pts = [v.co for f in faces for v in f.verts]
    principal = axe_principal(pts)
    travers = Vector((-principal.y, principal.x, 0.0))

    def couper(normale, d):
        faces = piece_courante()
        geom = set(faces)
        for f in faces:
            geom.update(f.verts)
            geom.update(f.edges)
        return bmesh.ops.bisect_plane(bm, geom=list(geom), dist=1e-4,
                                      plane_co=tuple(normale * d),
                                      plane_no=tuple(normale))

    # D'ABORD la limite du decouvert, sans monter de cloison : elle sert de
    # frontiere. Sans elle, chaque refend traversait la piece de part en part et
    # son milieu tombait pile sur le faitage — le test "suis-je a decouvert ?"
    # jouait alors a pile ou face, et six refends sur sept disparaissaient.
    bord = bord_du_decouvert(pts, travers, decouvert)
    if bord is not None:
        couper(travers, bord)

    lo = min(p.dot(principal) for p in pts)
    hi = max(p.dot(principal) for p in pts)
    plans = [(principal, lo + PAS_CLOISON * k)
             for k in range(1, int((hi - lo) / PAS_CLOISON) + 1)]

    poses = 0
    for normale, d in plans:
        res = couper(normale, d)
        aretes = [g for g in res["geom_cut"] if isinstance(g, bmesh.types.BMEdge)
                  and dans_le_decouvert((g.verts[0].co + g.verts[1].co) / 2,
                                        decouvert)]
        if not aretes:
            continue
        haut = bmesh.ops.extrude_edge_only(bm, edges=aretes)
        verts = [g for g in haut["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=verts, vec=(0, 0, HAUTEUR_CLOISON))
        poses += 1
    return poses


def ouvrir(obj, vers_camera: Vector) -> tuple[int, float]:
    """Retire les pans de toit qui regardent la camera et pose un plancher.

    Renvoie (nombre de pans retires, part de l'emprise laissee a decouvert).
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    zs = [v.co.z for v in bm.verts]
    zmin, zmax = min(zs), max(zs)
    seuil = zmin + 0.55 * (zmax - zmin)

    pans = [f for f in bm.faces
            if PENTE_MIN < f.normal.z < PENTE_MAX
            and f.calc_center_median().z > seuil
            and Vector((f.normal.x, f.normal.y)).dot(vers_camera) > FACE_CAMERA_MIN]
    if not pans:
        bm.free()
        return 0, 0.0

    aire_ouverte = sum(f.calc_area() for f in pans)
    egout = min(v.co.z for f in pans for v in f.verts)
    decouvert = []
    for f in pans:
        co = [v.co for v in f.verts]
        for a, b in zip(co[1:-1], co[2:]):
            decouvert.append(((co[0].x, co[0].y), (a.x, a.y), (b.x, b.y)))
    bmesh.ops.delete(bm, geom=pans, context="FACES")

    # plancher : l'emprise du batiment, recopiee a la hauteur de l'egout
    bas = faces_du_bas(bm, zmin)
    aire_sol = sum(f.calc_area() for f in bas)
    if bas:
        copie = bmesh.ops.duplicate(bm, geom=bas)
        neuves = [g for g in copie["geom"] if isinstance(g, bmesh.types.BMFace)]
        verts = {v for f in neuves for v in f.verts}
        bmesh.ops.translate(bm, verts=list(verts),
                            vec=(0, 0, egout - zmin - JEU_PLANCHER))
        envers = [f for f in neuves if f.normal.z < 0]
        if envers:
            bmesh.ops.reverse_faces(bm, faces=envers)   # un plancher regarde en haut
        epaissir_les_murs(bm, neuves)
        z_piece = egout - JEU_PLANCHER - EPAISSEUR_MUR
        poser_cloisons(bm, z_piece, decouvert)

    bm.to_mesh(obj.data)
    bm.free()
    return len(pans), (aire_ouverte / aire_sol if aire_sol else 0.0)


def choisir(cfg: dict, nombre: int, ecart: float) -> list[dict]:
    """Refabrique la selection depuis le fichier OSM. Voir le docstring."""
    import xml.etree.ElementTree as ET
    from collections import defaultdict

    POIDS = {"nightclub": 5, "bar": 5, "cafe": 5, "pub": 5, "restaurant": 4,
             "bakery": 4, "pharmacy": 4, "butcher": 4, "seafood": 4,
             "chocolate": 4, "jewelry": 3, "bank": 3, "fast_food": 3,
             "alcohol": 3, "newsagent": 3, "hairdresser": 2, "optician": 2,
             "houseware": 2, "leather": 2, "dry_cleaning": 2}
    DEHORS = {"bench", "waste_basket", "bicycle_parking", "recycling", "parking",
              "drinking_water", "fountain", "taxi", "bicycle_rental", "post_box",
              "atm", "clock", "shelter"}
    CLES = ("amenity", "shop", "craft", "office", "tourism", "historic", "leisure")

    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    racine = ET.parse(ROOT / cfg["import"]["source_osm"]).getroot()
    noeuds = {n.get("id"): (float(n.get("lat")), float(n.get("lon")))
              for n in racine.iter("node")}

    def etiquettes(e):
        return {t.get("k"): t.get("v") for t in e.findall("tag")}

    def usage(t):
        for k in CLES:
            if k in t:
                return t[k]
        return "?"

    def interieur(t):
        if t.get("man_made"):
            return False
        if any(k in t for k in ("shop", "craft", "office")):
            return True
        return any(t.get(k) and t[k] not in DEHORS
                   for k in ("amenity", "tourism", "historic", "leisure"))

    pois = []
    for n in racine.iter("node"):
        t = etiquettes(n)
        la, lo = noeuds[n.get("id")]
        if interieur(t) and lat0 <= la <= lat1 and lon0 <= lo <= lon1:
            pois.append((lo, la, t))

    emprises = {}
    for w in racine.iter("way"):
        if "building" not in etiquettes(w):
            continue
        pts = [(noeuds[nd.get("ref")][1], noeuds[nd.get("ref")][0])
               for nd in w.findall("nd") if nd.get("ref") in noeuds]
        if len(pts) < 4:
            continue
        if not (lat0 <= sum(p[1] for p in pts) / len(pts) <= lat1
                and lon0 <= sum(p[0] for p in pts) / len(pts) <= lon1):
            continue
        emprises[w.get("id")] = pts

    def dedans(p, poly):
        x, y = p
        ok, j = False, len(poly) - 1
        for i in range(len(poly)):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                ok = not ok
            j = i
        return ok

    dans = defaultdict(list)
    for x, y, t in pois:
        for wid, pts in emprises.items():
            if dedans((x, y), pts):
                dans[wid].append(t)
                break

    pos, cote = {}, {}
    for wid in dans:
        obj = bpy.data.objects.get(f"building.{wid}")
        if obj is None or not obj.data.vertices:
            continue
        bas = [obj.matrix_world @ v.co for v in obj.data.vertices
               if (obj.matrix_world @ v.co).z < 0.6]
        if not bas:
            continue
        pos[wid] = (sum(p.x for p in bas) / len(bas), sum(p.y for p in bas) / len(bas))
        cote[wid] = math.sqrt(max(1.0, (max(p.x for p in bas) - min(p.x for p in bas))
                                  * (max(p.y for p in bas) - min(p.y for p in bas))))

    note = {w: max(POIDS.get(usage(t), 1) for t in ts) * cote[w]
            for w, ts in dans.items() if w in pos}
    retenus = []
    for w in sorted(note, key=lambda k: -note[k]):
        if all(math.dist(pos[w], pos[c["osm"]]) >= ecart for c in retenus):
            retenus.append({"osm": w, "usage": usage(dans[w][0])})
        if len(retenus) >= nombre:
            break
    return retenus


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_pave.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_ouvert.blend")
    p.add_argument("--choisir", action="store_true",
                   help="refabriquer la selection et l'afficher, sans rien ecrire")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))

    ouverts = cfg["zone"].get("toits_ouverts", {})
    if args.choisir:
        liste = choisir(cfg, ouverts.get("nombre", 10), ouverts.get("ecart_min_m", 35.0))
        print(json.dumps(liste, indent=1, ensure_ascii=False))
        return 0

    liste = ouverts.get("liste", [])
    if not liste:
        print("[ouvertures] aucune liste dans config.json : rien a ouvrir")
        bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
        return 0

    vers_camera = direction_camera(cfg["camera"]["rotation_z_deg"])
    faits = 0
    for lieu in liste:
        obj = bpy.data.objects.get(f"building.{lieu['osm']}")
        if obj is None:
            print(f"[ouvertures] {lieu['osm']} introuvable")
            continue
        pans, part = ouvrir(obj, vers_camera)
        if pans:
            faits += 1
        print(f"[ouvertures] {lieu.get('nom', lieu['osm']):26s} "
              f"{pans} pan(s) retire(s), {100 * part:4.0f} % de l'emprise a ciel ouvert")
    print(f"[ouvertures] {faits}/{len(liste)} lieux ouverts sur "
          f"{len([o for o in bpy.data.collections['buildings'].objects])} batiments")

    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[ouvertures] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
