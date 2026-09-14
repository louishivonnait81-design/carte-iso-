"""Etape 7 — les facades : ouvertures, portes, corniches, arcades.

    blender -b -P v2/07_facades.py

Lit castres_toits.blend, ecrit castres_facades.blend.

LES OUVERTURES NE SONT PAS CREUSEES DANS LE MUR. Elles sont posees dessus, en
quads decolles de trois centimetres, reunis dans un seul objet. Trois raisons :

  * creuser demanderait un booleen par fenetre — des milliers d'operations, et
    autant d'occasions de produire une geometrie non manifold ;
  * Freestyle dessine le BORD d'un maillage : un quad pose suffit a obtenir le
    trait de l'ouverture, qui est tout ce qu'on lui demande ;
  * un seul objet pour toute la ville se cache ou se remplace d'un geste, ce qui
    rend le reglage du rythme des travees rejouable sans toucher au bati.

Le rythme est deduit de la geometrie, jamais tire au hasard : hauteur d'etage
fixe, travees reparties regulierement sur la largeur reelle du mur. Deux murs de
meme longueur recoivent donc le meme nombre de travees, ce qui est precisement
ce qu'on veut d'une rue.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

V2 = Path(__file__).resolve().parent
ROOT = V2.parent
CONFIG = V2 / "config.json"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from geo import latlon_to_xy  # noqa: E402

DECOLLEMENT = 0.03      # m, pour que le quad ne z-fighte pas avec le mur
ETAGE_M = 3.2           # hauteur d'un niveau
TRAVEE_M = 3.0          # entraxe vise entre deux travees
FENETRE = (0.95, 1.55)  # largeur, hauteur
PORTE = (1.10, 2.20)
MUR_MIN_LARGEUR = 2.6   # m, en deca aucune travee ne tient
MUR_MIN_AIRE = 5.0      # m2
CORNICHE = 0.25         # m, hauteur du bandeau sous l'egout
ARCADE_H = 3.4          # m, hauteur totale d'une arche
ARCADE_L = 2.6          # m, largeur d'une arche
BORD_PLACE = 3.0        # m, distance au polygone de la place


def polygone_place(cfg: dict, scene, nom: str):
    """Contour de la place, en coordonnees Blender."""
    osm = ROOT / cfg["import"]["source_osm"]
    if not osm.exists():
        return []
    olat, olon = scene.get("lat"), scene.get("lon")
    voulu, nodes, pts = nom.lower(), {}, []
    for _, el in ET.iterparse(osm, events=("end",)):
        if el.tag == "node":
            nodes[int(el.get("id"))] = (float(el.get("lat")), float(el.get("lon")))
            el.clear()
        elif el.tag == "way":
            etiquette = next((t.get("v") for t in el.findall("tag")
                              if t.get("k") == "name"), None)
            place = any(t.get("k") == "place" and t.get("v") == "square"
                        for t in el.findall("tag"))
            if etiquette and etiquette.lower() == voulu and place:
                refs = [int(n.get("ref")) for n in el.findall("nd")]
                pts = [latlon_to_xy(*nodes[r], olat, olon) for r in refs if r in nodes]
            el.clear()
    return pts


def distance_au_contour(x: float, y: float, contour) -> float:
    if len(contour) < 2:
        return 1e9
    best = 1e9
    n = len(contour)
    for i in range(n):
        ax, ay = contour[i]
        bx, by = contour[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        if dx == 0.0 and dy == 0.0:
            continue
        s = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - ax - s * dx, y - ay - s * dy))
    return best


def quad(bm, origine, u, v, largeur, hauteur, normale):
    """Rectangle pose sur le mur, decolle vers l'exterieur."""
    base = origine + normale * DECOLLEMENT
    coins = [base, base + u * largeur, base + u * largeur + v * hauteur,
             base + v * hauteur]
    bm.faces.new([bm.verts.new(c) for c in coins])


def arche(bm, origine, u, v, largeur, hauteur, normale, segments: int = 8):
    """Baie en plein cintre : piedroits droits, demi-cercle au-dessus."""
    base = origine + normale * DECOLLEMENT
    rayon = largeur / 2.0
    droit = max(0.2, hauteur - rayon)
    pts = [base, base + u * largeur, base + u * largeur + v * droit]
    centre = base + u * rayon + v * droit
    for i in range(1, segments):
        a = math.pi * i / segments
        pts.append(centre + u * (rayon * math.cos(a)) + v * (rayon * math.sin(a)))
    pts.append(base + v * droit)
    bm.faces.new([bm.verts.new(p) for p in pts])


def devanture(bm, origine, u, v, largeur, hauteur, normale):
    """Vitrine en retrait sous une arche : cadre, traverse, porte.

    Sous l'arcade de la place, les baies etaient des trous vides. Une vitrine ne
    se creuse pas non plus : un cadre pose a l'interieur du contour de l'arche
    suffit a la lire, et la traverse a hauteur d'imposte suffit a la dater.
    """
    retrait = 0.28
    l = largeur - 2 * retrait
    h = hauteur - 1.1
    if l < 0.8 or h < 1.4:
        return 0
    base = origine + u * retrait + v * 0.15
    quad(bm, base, u, v, l, h, normale)
    # traverse d'imposte, a hauteur de porte
    quad(bm, base + v * (h * 0.62), u, v, l, 0.10, normale)
    return 2


def murs(obj):
    """Faces verticales assez grandes pour porter des ouvertures."""
    for face in obj.data.polygons:
        n = face.normal
        if abs(n.z) > 0.3 or face.area < MUR_MIN_AIRE:
            continue
        yield face


def habiller(obj, bm_out, contour_place) -> int:
    """Pose les ouvertures d'un batiment. Renvoie le nombre de quads crees."""
    mat = obj.matrix_world
    poses = 0
    for face in murs(obj):
        coords = [mat @ Vector(obj.data.vertices[i].co) for i in face.vertices]
        normale = (mat.to_3x3() @ face.normal).normalized()
        u = Vector((-normale.y, normale.x, 0.0))
        if u.length < 1e-6:
            continue
        u.normalize()
        v = Vector((0.0, 0.0, 1.0))

        us = [c.dot(u) for c in coords]
        zs = [c.z for c in coords]
        largeur, bas, haut = max(us) - min(us), min(zs), max(zs)
        hauteur = haut - bas
        if largeur < MUR_MIN_LARGEUR or hauteur < 3.0:
            continue

        # origine du mur : le coin bas-gauche, dans le plan de la face
        ancre = coords[us.index(min(us))]
        origine = Vector((ancre.x, ancre.y, bas)) - u * 0.0

        centre = sum(coords, Vector()) / len(coords)
        sur_la_place = (distance_au_contour(centre.x, centre.y, contour_place)
                        <= BORD_PLACE)

        travees = max(1, int(largeur // TRAVEE_M))
        pas = largeur / travees
        niveaux = max(1, int((hauteur - 0.6) // ETAGE_M))

        for t in range(travees):
            u0 = (t + 0.5) * pas
            for n in range(niveaux):
                z0 = bas + 0.6 + n * ETAGE_M
                if n == 0 and sur_la_place:
                    if pas < ARCADE_L + 0.4 or hauteur < ARCADE_H + 1.0:
                        continue
                    pied = origine + u * (u0 - ARCADE_L / 2) + v * (z0 - bas - 0.3)
                    arche(bm_out, pied, u, v, ARCADE_L, ARCADE_H, normale)
                    poses += devanture(bm_out, pied, u, v,
                                       ARCADE_L, ARCADE_H, normale)
                elif n == 0 and t == travees // 2:
                    l, h = PORTE
                    arche(bm_out, origine + u * (u0 - l / 2) + v * (z0 - bas - 0.5),
                          u, v, l, h, normale)
                elif n == 0:
                    # rez-de-chaussee ordinaire : une devanture, pas une fenetre
                    l, h = min(2.10, pas - 0.6), 2.30
                    if l > 1.0:
                        quad(bm_out,
                             origine + u * (u0 - l / 2) + v * (z0 - bas - 0.3),
                             u, v, l, h, normale)
                        quad(bm_out,
                             origine + u * (u0 - l / 2) + v * (z0 - bas - 0.3 + h),
                             u, v, l, 0.14, normale)   # bandeau d'enseigne
                        poses += 1
                else:
                    l, h = FENETRE
                    quad(bm_out, origine + u * (u0 - l / 2) + v * (z0 - bas + 0.5),
                         u, v, l, h, normale)
                poses += 1

        # corniche : un bandeau continu sous l'egout
        quad(bm_out, origine + v * (hauteur - CORNICHE - 0.1), u, v,
             largeur, CORNICHE, normale)
        poses += 1
    return poses



def _ranger(scene, objet, nom_collection: str):
    """Range l'objet dans une collection NOMMEE.

    Ce n'est pas du rangement : c'est ce qui permet a Freestyle de lui donner sa
    propre epaisseur de trait. Sans collection, tout le dessin sort au meme
    poids de ligne — le joint de dallage aussi fort que le mur — et la
    hierarchie qui fait lire un dessin au trait disparait.
    """
    coll = bpy.data.collections.get(nom_collection)
    if coll is None:
        coll = bpy.data.collections.new(nom_collection)
        scene.collection.children.link(coll)
    coll.objects.link(objet)
    return objet


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_toits.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_facades.blend")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene

    contour = polygone_place(cfg, scene, cfg["zone"]["coeur"]["centre"])
    print(f"[facades] contour de la place : {len(contour)} sommets")

    coll = bpy.data.collections.get("buildings")
    bm = bmesh.new()
    total = 0
    for obj in list(coll.objects):
        if obj.type == "MESH" and obj.data.polygons:
            total += habiller(obj, bm, contour)

    mesh = bpy.data.meshes.new("V2_FACADES")
    bm.to_mesh(mesh)
    bm.free()
    objet = bpy.data.objects.new("V2_FACADES", mesh)
    _ranger(scene, objet, "facades")

    print(f"[facades] {total} ouvertures posees, {len(mesh.vertices)} sommets")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[facades] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
