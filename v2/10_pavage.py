"""Etape 10 — le pavage de la place, la nappe d'eau, les emmarchements.

    blender -b -P v2/10_pavage.py

Lit castres_final.blend, ecrit castres_pave.blend.

La place est la plus grande surface de la carte et la seule entierement vide :
un aplat blanc de plusieurs milliers de metres carres, sur lequel l'oeil n'a
rien a se poser. Elle recoit donc son appareillage.

Les joints sont poses comme les ouvertures de l'etape 7 : des quads decolles,
reunis dans un seul objet. Freestyle en dessine le bord, ce qui suffit, et
regler l'entraxe ne demande pas de retoucher le sol.

L'ORIENTATION DES BANDES N'EST PAS CHOISIE, ELLE EST MESUREE. On prend l'axe
long du rectangle englobant de la place : un pavage suit la forme de l'espace
qu'il couvre, et une place en longueur se lit dans sa longueur.

LA NAPPE D'EAU entoure la statue parce que la photo le montre — Jaures se
dresse au milieu d'un plan d'eau peu profond, et la "fontaine" que les donnees
OSM placent a un metre de lui est cette nappe, pas un objet distinct. Elle est
donc posee AUTOUR des memoriaux, et nulle part ailleurs.
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

# Entraxe des joints, dans LES DEUX SENS. Premiere version : seulement des
# joints longitudinaux, a 2,4 m. Resultat, des lignes de 112 m d'un seul tenant
# qui lisaient comme des rails et non comme un sol. Le pavage de la place est en
# dalles, et une dalle a deux dimensions : il faut les joints transversaux.
ENTRAXE = 3.2
JOINT = 0.10            # m, largeur du trait de joint
Z_JOINT = 0.18          # au-dessus du sol pietonnier (14 cm) sans le toucher
NAPPE_R = 4.2           # m, demi-cote de la nappe d'eau autour d'un memorial
NAPPE_MARGE = 0.55      # m, largeur de la margelle


def contour_place(cfg: dict, scene, nom: str):
    osm = ROOT / cfg["import"]["source_osm"]
    olat, olon = scene.get("lat"), scene.get("lon")
    voulu, nodes, pts = nom.lower(), {}, []
    for _, el in ET.iterparse(osm, events=("end",)):
        if el.tag == "node":
            nodes[int(el.get("id"))] = (float(el.get("lat")), float(el.get("lon")))
            el.clear()
        elif el.tag == "way":
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            if (tags.get("name", "").lower() == voulu
                    and tags.get("place") == "square"):
                refs = [int(n.get("ref")) for n in el.findall("nd")]
                pts = [latlon_to_xy(*nodes[r], olat, olon) for r in refs if r in nodes]
            el.clear()
    return pts


def axe_long(points):
    """Angle de l'axe long du rectangle englobant minimal, et ses dimensions."""
    meilleur = None
    n = len(points)
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        a = -math.atan2(by - ay, bx - ax)
        c, s = math.cos(a), math.sin(a)
        xs = [x * c - y * s for x, y in points]
        ys = [x * s + y * c for x, y in points]
        l, p = max(xs) - min(xs), max(ys) - min(ys)
        if meilleur is None or l * p < meilleur[0]:
            meilleur = (l * p, l, p, a, min(xs), min(ys))
    _, l, p, a, x0, y0 = meilleur
    return (a if l >= p else a + math.pi / 2), max(l, p), min(l, p)


def dans_polygone(x, y, contour) -> bool:
    dedans = False
    n = len(contour)
    for i in range(n):
        ax, ay = contour[i]
        bx, by = contour[(i + 1) % n]
        if (ay > y) != (by > y) and x < ax + (y - ay) / (by - ay + 1e-12) * (bx - ax):
            dedans = not dedans
    return dedans


def bande(bm, centre, direction, longueur, largeur, z):
    u = direction
    v = Vector((-u.y, u.x, 0.0))
    demi_l, demi_w = longueur / 2, largeur / 2
    coins = [centre + u * demi_l + v * demi_w, centre - u * demi_l + v * demi_w,
             centre - u * demi_l - v * demi_w, centre + u * demi_l - v * demi_w]
    bm.faces.new([bm.verts.new((c.x, c.y, z)) for c in coins])


def paver(bm, contour) -> int:
    """Grille de joints suivant l'axe long de la place, dans les deux sens."""
    angle, longueur, largeur = axe_long(contour)
    u = Vector((math.cos(angle), math.sin(angle), 0.0))
    v = Vector((-u.y, u.x, 0.0))
    cx = sum(p[0] for p in contour) / len(contour)
    cy = sum(p[1] for p in contour) / len(contour)
    centre = Vector((cx, cy, 0.0))

    poses = 0
    for sens, (direction, perpendiculaire, portee, etendue) in enumerate((
            (u, v, longueur, largeur), (v, u, largeur, longueur))):
        poses += _lignes(bm, contour, centre, direction, perpendiculaire,
                         portee, etendue)
    return poses


def _lignes(bm, contour, centre, u, v, longueur, largeur) -> int:
    """Une famille de joints paralleles, decoupee aux bords de la place."""
    poses = 0
    combien = int(largeur // ENTRAXE)
    for i in range(-combien // 2, combien // 2 + 1):
        depart = centre + v * (i * ENTRAXE)
        # on ne trace que les tronçons qui tombent DANS la place
        pas = 1.0
        n = int(longueur / pas)
        debut = None
        for k in range(n + 1):
            p = depart + u * (-longueur / 2 + k * pas)
            if dans_polygone(p.x, p.y, contour):
                debut = p if debut is None else debut
            elif debut is not None:
                milieu = (debut + p) / 2
                if (p - debut).length > 1.5:
                    bande(bm, milieu, u, (p - debut).length, JOINT, Z_JOINT)
                    poses += 1
                debut = None
        if debut is not None:
            fin = depart + u * (longueur / 2)
            if (fin - debut).length > 1.5:
                bande(bm, (debut + fin) / 2, u, (fin - debut).length, JOINT, Z_JOINT)
                poses += 1
    return poses


def nappe(bm, x, y, z=0.02) -> None:
    """Plan d'eau peu profond a margelle, autour d'un memorial."""
    for demi, hauteur in ((NAPPE_R, z), (NAPPE_R - NAPPE_MARGE, z - 0.10)):
        coins = [(x - demi, y - demi), (x + demi, y - demi),
                 (x + demi, y + demi), (x - demi, y + demi)]
        bm.faces.new([bm.verts.new((cx, cy, hauteur)) for cx, cy in coins])


def memoriaux(cfg: dict, scene):
    osm = ROOT / cfg["import"]["source_osm"]
    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    olat, olon = scene.get("lat"), scene.get("lon")
    out = []
    for _, el in ET.iterparse(osm, events=("end",)):
        if el.tag != "node":
            continue
        lat, lon = float(el.get("lat")), float(el.get("lon"))
        if lat0 <= lat <= lat1 and lon0 <= lon <= lon1:
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            if tags.get("historic") in {"memorial", "monument"}:
                out.append(latlon_to_xy(lat, lon, olat, olon))
        el.clear()
    return out


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_final.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_pave.blend")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene

    contour = contour_place(cfg, scene, cfg["zone"]["coeur"]["centre"])
    if len(contour) < 3:
        sys.exit("Contour de la place introuvable.")
    angle, longueur, largeur = axe_long(contour)
    print(f"[pavage] place : {longueur:.0f} x {largeur:.0f} m, "
          f"axe long a {math.degrees(angle) % 180:.0f} deg")

    bm = bmesh.new()
    joints = paver(bm, contour)
    eaux = memoriaux(cfg, scene)
    for x, y in eaux:
        nappe(bm, x, y)

    mesh = bpy.data.meshes.new("V2_PAVAGE")
    bm.to_mesh(mesh)
    bm.free()
    scene.collection.objects.link(bpy.data.objects.new("V2_PAVAGE", mesh))

    print(f"[pavage] {joints} joints, {len(eaux)} nappes d'eau")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[pavage] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
