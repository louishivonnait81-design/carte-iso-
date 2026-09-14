"""Etape 6 — les toitures, posees sur des prismes nus.

    blender -b -P v2/06_toits.py

Lit castres_sol.blend, ecrit castres_toits.blend.

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
COTE_MIN_CROUPE = 4.0   # m ; sous cette largeur l'inset degenere
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
    aire, largeur, profondeur, _ = rectangle_oriente(points)
    petit = min(largeur, profondeur)
    remplissage = aire_polygone(points) / aire if aire else 0.0

    if (remplissage >= REMPLISSAGE_MIN and petit >= COTE_MIN_CROUPE
            and len(points) <= 10 and est_convexe(points)):
        inset = 0.48 * petit
        montee = min(MONTEE_MAX, PENTE * inset)
        bmesh.ops.inset_region(bm, faces=dessus, thickness=inset, depth=montee,
                               use_even_offset=True, use_boundary=True)
        cas = "croupe"
    else:
        # acrotere : un muret de rive. Une ligne franche au lieu d'une croupe
        # inventee sur une emprise que l'on ne sait pas lire.
        resultat = bmesh.ops.inset_region(bm, faces=dessus,
                                          thickness=RETRAIT_ACROTERE, depth=0.0,
                                          use_even_offset=True, use_boundary=True)
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
    p.add_argument("--blend", type=Path, default=V2 / "castres_sol.blend")
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
