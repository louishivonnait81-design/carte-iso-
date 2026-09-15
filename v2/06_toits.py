"""Etape 6 — les toitures, posees sur des prismes nus.

    blender -b -P v2/06_toits.py

Lit castres_rues.blend, ecrit castres_toits.blend.

POURQUOI UNE ETAPE A PART. L'importateur sait poser des croupes, mais sur une
emprise irreguliere l'inset des versants degenere : la face du dessus se replie,
et Freestyle dessine consciencieusement le desordre. On importe donc des prismes
a toit plat et on pose la toiture ici, ou l'on peut decider AU CAS PAR CAS.

TROIS CAS, ET LE TROISIEME EST LE PLUS IMPORTANT.

  * emprise reguliere et assez large -> une croupe, avec un vrai faitage ;
  * emprise reguliere mais etroite   -> deux versants, sans faitage transversal ;
  * emprise irreguliere              -> TOIT PLAT A ACROTERE. Pas un pis-aller :
    un coeur d'ilot est fait de courettes, d'appentis et de volumes biscornus
    dont la toiture reelle est un patchwork illisible a cette echelle. Une ligne
    d'acrotere nette vaut mieux qu'une croupe inventee.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

V2 = Path(__file__).resolve().parent

# Un versant de tuile canal monte doucement : environ 28 degres, soit une
# elevation de 0,53 fois la demi-largeur.
PENTE = 0.53
MONTEE_MAX = 3.0        # m, au-dela le toit ecrase la facade
PART_MONTEE_MAX = 0.45  # la toiture ne depasse jamais cette part de la hauteur du mur
COTE_MIN_CROUPE = 4.0   # m ; sous cette largeur l'inset degenere
COTE_MIN_FAITAGE = 3.0  # m ; sous cette largeur un faitage ne se lit plus
CARRE_MAX = 1.6         # au-dela de ce rapport long/court, on fait un faitage
TOLERANCE_DEBORD = 0.5   # m ; au-dela, l'inset s'est replie : on refait autrement
REMPLISSAGE_MIN = 0.72  # part de son rectangle englobant qu'une emprise doit remplir
ACROTERE = 0.35         # m, hauteur du muret de rive d'un toit plat
RETRAIT_ACROTERE = 0.30  # m


def faces_du_dessus(bm, tolerance: float = 0.05):
    """TOUTES les faces horizontales du niveau le plus haut.

    Pas une seule : les maillages sont triangules, et prendre la face la plus
    grande ne donnait qu'UN TRIANGLE du toit. Mesure du symptome : la face
    retenue avait 3 sommets en mediane et remplissait exactement 0,50 de son
    rectangle englobant — la signature d'un triangle. Le test de regularite
    echouait donc sur 99 % des batiments, et tous recevaient un acrotere.
    """
    hautes = [f for f in bm.faces if f.normal.z > 0.9]
    if not hautes:
        return []
    zmax = max(f.calc_center_median().z for f in hautes)
    return [f for f in hautes if zmax - f.calc_center_median().z <= tolerance]


def contour(faces):
    """Sommets du bord exterieur d'une region de faces, dans l'ordre."""
    dedans = set(faces)
    bords = [e for f in faces for e in f.edges
             if sum(1 for lf in e.link_faces if lf in dedans) == 1]
    if not bords:
        return []
    suivant = {}
    for e in bords:
        a, b = e.verts
        suivant.setdefault(a, []).append(b)
        suivant.setdefault(b, []).append(a)
    depart = bords[0].verts[0]
    boucle, vu, courant, precedent = [depart], {depart}, depart, None
    while True:
        candidats = [v for v in suivant.get(courant, []) if v is not precedent]
        suite = next((v for v in candidats if v not in vu), None)
        if suite is None:
            break
        boucle.append(suite)
        vu.add(suite)
        precedent, courant = courant, suite
    return boucle


def rectangle_oriente(points):
    """(aire, largeur, profondeur, angle) du rectangle englobant minimal."""
    meilleur = None
    n = len(points)
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        angle = -math.atan2(by - ay, bx - ax)
        c, s = math.cos(angle), math.sin(angle)
        xs = [x * c - y * s for x, y in points]
        ys = [x * s + y * c for x, y in points]
        l, p = max(xs) - min(xs), max(ys) - min(ys)
        if meilleur is None or l * p < meilleur[0]:
            meilleur = (l * p, l, p, angle)
    return meilleur


def est_convexe(points, tolerance: float = 0.02) -> bool:
    """Vrai si le polygone ne rentre nulle part vers l'interieur.

    Le remplissage du rectangle englobant ne suffit pas : un L bien proportionne
    en remplit 0,75 et passait le test, alors que l'inset d'une croupe sur un
    angle rentrant se replie sur lui-meme et part en facettes. C'est ce qui
    restait de desordre sur les toits apres la premiere correction.
    """
    n = len(points)
    if n < 4:
        return True
    signe = 0
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        cx, cy = points[(i + 2) % n]
        croix = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        longueur = math.hypot(bx - ax, by - ay) * math.hypot(cx - bx, cy - by)
        if longueur < 1e-9 or abs(croix) < tolerance * longueur:
            continue                     # sommets alignes : sans effet
        courant = 1 if croix > 0 else -1
        if signe and courant != signe:
            return False
        signe = courant
    return True


def aire_polygone(points) -> float:
    return abs(0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                         in zip(points, points[1:] + points[:1])))


def debordement(bm, points) -> float:
    """De combien de metres le maillage deborde-t-il de son emprise de depart ?

    Un inset "even" qui se replie envoie un sommet tres loin, et rien dans la
    forme ne l'annonce a coup sur : le batiment 83182684 est convexe, remplit
    0,86 de son rectangle, n'a pas d'angle sous 78 degres — et son sommet
    partait a 141 m. On mesure donc le resultat au lieu de le prevoir.
    """
    x0 = min(x for x, _ in points)
    x1 = max(x for x, _ in points)
    y0 = min(y for _, y in points)
    y1 = max(y for _, y in points)
    return max(max(x0 - v.co.x, v.co.x - x1, y0 - v.co.y, v.co.y - y1)
               for v in bm.verts)


def poser_deux_versants(bm, dessus, centre, angle, petit, hauteur_mur) -> bool:
    """Un faitage sur l'axe long, deux versants qui tombent sur les cotes longs.

    Marche sur n'IMPORTE QUELLE emprise, y compris en L : on ne construit pas de
    geometrie nouvelle, on COUPE la face du dessus le long de l'axe et on remonte
    chaque sommet selon sa distance a cet axe. Un angle rentrant ne peut donc pas
    faire se replier l'inset, puisqu'il n'y a pas d'inset.

    C'est ce qui manquait : 42 batiments echouaient sur le seul critere d'angle
    rentrant, et 187 sur 264 finissaient en toit plat a acrotere — un coeur de
    ville ancienne entierement en terrasses.
    """
    axe = Vector((math.cos(angle), math.sin(angle), 0.0))
    normale = Vector((-axe.y, axe.x, 0.0))
    zmax = max(v.co.z for f in dessus for v in f.verts)

    geom = set()
    for f in dessus:
        geom.add(f)
        geom.update(f.verts)
        geom.update(f.edges)
    bmesh.ops.bisect_plane(bm, geom=list(geom), dist=1e-4,
                           plane_co=(centre.x, centre.y, zmax),
                           plane_no=tuple(normale))

    hauts = [v for v in bm.verts if abs(v.co.z - zmax) < 1e-3]
    if not hauts:
        return False
    demi = petit / 2.0
    montee = min(MONTEE_MAX, PENTE * demi, PART_MONTEE_MAX * hauteur_mur)
    for v in hauts:
        d = abs((v.co - Vector((centre.x, centre.y, zmax))).dot(normale))
        v.co.z += montee * max(0.0, 1.0 - d / demi)
    return True


def poser_toit(obj) -> str:
    """Pose une toiture sur un prisme. Renvoie le cas choisi."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    dessus = faces_du_dessus(bm)
    if not dessus:
        bm.free()
        return "aucune"
    boucle = contour(dessus)
    if len(boucle) < 3:
        bm.free()
        return "aucune"

    points = [(v.co.x, v.co.y) for v in boucle]
    # a 4,6 m de mur moyen, un comble de 3 m ferait une tente : la toiture est
    # bornee par la hauteur du mur autant que par la largeur de l'emprise
    hauteur_mur = max(v.co.z for v in bm.verts) - min(v.co.z for v in bm.verts)
    aire, largeur, profondeur, angle_bb = rectangle_oriente(points)
    petit = min(largeur, profondeur)
    remplissage = aire_polygone(points) / aire if aire else 0.0

    grand = max(largeur, profondeur)
    carre = grand / petit if petit > 1e-6 else 99.0

    cas = None
    if (carre <= CARRE_MAX and remplissage >= REMPLISSAGE_MIN
            and petit >= COTE_MIN_CROUPE and len(points) <= 10
            and est_convexe(points)):
        # emprise ramassee : une croupe, quatre pans qui se rejoignent
        inset = 0.48 * petit
        montee = min(MONTEE_MAX, PENTE * inset, PART_MONTEE_MAX * hauteur_mur)
        bmesh.ops.inset_region(bm, faces=dessus, thickness=inset, depth=montee,
                               use_even_offset=True, use_boundary=True)
        if debordement(bm, points) <= TOLERANCE_DEBORD:
            cas = "croupe"
        else:
            # l'offset s'est replie sur lui-meme. Aucun critere de forme ne
            # l'annonce a coup sur : on le CONSTATE et on refait un faitage, qui
            # ne deplace aucun sommet dans le plan.
            bm.free()
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            dessus = faces_du_dessus(bm)

    if cas is None and petit >= COTE_MIN_FAITAGE:
        centre = Vector((sum(x for x, _ in points) / len(points),
                         sum(y for _, y in points) / len(points), 0.0))
        # rectangle_oriente rend l'angle qui remet le cote sur X : l'axe long
        # est donc X ou Y selon lequel des deux cotes est le plus grand
        axe = -angle_bb if largeur >= profondeur else -angle_bb + math.pi / 2
        cas = "faitage" if poser_deux_versants(bm, dessus, centre, axe, petit,
                                               hauteur_mur) \
            else "acrotere"
        if cas == "acrotere":
            dessus = faces_du_dessus(bm)
    elif cas is None:
        # acrotere : un muret de rive. Une ligne franche au lieu d'une croupe
        # inventee sur une emprise que l'on ne sait pas lire.
        # PAS d'offset "even" ici, et une epaisseur bornee par l'emprise. Le
        # decalage even divise par sin(angle/2) : sur une emprise en lame de
        # couteau — il en reste, ce sont des epaisseurs de mur saisies comme des
        # batiments — il envoyait des sommets a 250 m de la zone, et Freestyle
        # tirait de longues diagonales en travers de la carte. Mesure : 8 objets
        # hors zone, jusqu'a 253,8 m, tous nes ici.
        retrait = min(RETRAIT_ACROTERE, 0.25 * petit)
        resultat = bmesh.ops.inset_region(bm, faces=dessus,
                                          thickness=retrait, depth=0.0,
                                          use_even_offset=False, use_boundary=True)
        # inset_region rend les faces du POURTOUR ; l'interieur est ce qui reste
        pourtour = set(resultat["faces"])
        interieur = [f for f in dessus if f.is_valid and f not in pourtour]
        verts = {v for f in interieur for v in f.verts}
        if verts:
            bmesh.ops.translate(bm, verts=list(verts), vec=(0, 0, -ACROTERE))
        cas = "acrotere"

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    return cas


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_rues.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_toits.blend")
    args = p.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    coll = bpy.data.collections.get("buildings")
    if coll is None:
        sys.exit("Pas de collection buildings : reprendre a l'etape 2.")

    compte = {}
    for obj in list(coll.objects):
        if obj.type != "MESH" or not obj.data.polygons:
            continue
        cas = poser_toit(obj)
        compte[cas] = compte.get(cas, 0) + 1

    total = sum(compte.values())
    for cas, n in sorted(compte.items(), key=lambda kv: -kv[1]):
        print(f"[toits] {cas:<10} {n:4d}  ({100 * n / total:4.1f} %)")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[toits] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
