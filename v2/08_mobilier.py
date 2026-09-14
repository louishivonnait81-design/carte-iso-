"""Etape 8 — arbres en volume et mobilier urbain.

    blender -b -P v2/08_mobilier.py

Lit castres_facades.blend, ecrit castres_mobilier.blend.

LES ARBRES. L'import les pose en disques PLATS. Vus a 60 degres un disque plat
se lit comme une tache, et c'est exactement ce que montraient les rendus
precedents : des ronds sur le sol. Les photos de la place donnent la forme
reelle — houppier rond et dense sur un tronc court, planté en rangees — d'ou une
sphere aplatie posee sur un fût, et non l'arbre haut et clair d'un platane.

LE MOBILIER vient des noeuds OSM de la zone, et de rien d'autre. Inventaire
mesure : 18 arbres, 14 range-velos, 8 bancs, 7 corbeilles, 5 bornes, 2
memoriaux, 2 arrets de bus, 1 boite aux lettres.

AUCUN LAMPADAIRE. Il n'y a pas un seul highway=street_lamp dans la zone. Les
photos en montrent, donc ils existent ; mais les placer demanderait de deviner
ou, et une carte ou l'on cherche un detail ne supporte pas le mobilier invente.
Le jour ou quelqu'un les saisit dans OSM, ils apparaitront sans changer une
ligne ici.

Chaque genre est modelise UNE FOIS et instancie : les objets partagent leur
maillage, si bien que regler la forme d'un banc les regle tous.
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

# Ce que l'on sait placer, et depuis quel tag. Ordre = priorite si un noeud en
# porte plusieurs.
GENRES = [
    (("natural", "tree"), "arbre"),
    (("historic", "memorial"), "statue"),
    (("historic", "monument"), "statue"),
    (("amenity", "bench"), "banc"),
    (("amenity", "bicycle_parking"), "velos"),
    (("amenity", "waste_basket"), "corbeille"),
    (("barrier", "bollard"), "borne"),
    (("amenity", "post_box"), "boite"),
    (("highway", "bus_stop"), "abri"),
]

HOUPPIER_R = 2.6        # m, rayon du houppier
HOUPPIER_APLAT = 0.72   # une boule aplatie, pas une sphere
TRONC_H = 2.1
TRONC_R = 0.16


def cube(bm, centre, dims, decalage=(0, 0, 0)):
    res = bmesh.ops.create_cube(bm, size=1.0)
    verts = res["verts"]
    bmesh.ops.scale(bm, verts=verts, vec=dims)
    bmesh.ops.translate(bm, verts=verts,
                        vec=(centre[0] + decalage[0], centre[1] + decalage[1],
                             centre[2] + decalage[2]))
    return verts


def cylindre(bm, centre, rayon, hauteur, segments=8):
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segments,
                                radius1=rayon, radius2=rayon, depth=hauteur)
    bmesh.ops.translate(bm, verts=res["verts"],
                        vec=(centre[0], centre[1], centre[2] + hauteur / 2))
    return res["verts"]


def maillage_arbre():
    """Houppier LISSE. En facettes, Freestyle dessine chaque arete de
    l'icosphere et l'arbre sort en polyedre. Lisse, il n'en reste que la
    silhouette : un rond, ce qui est exactement ce que montrent les photos et ce
    que demande le trait clair."""
    bm = bmesh.new()
    cylindre(bm, (0, 0, 0), TRONC_R, TRONC_H, segments=6)
    res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=HOUPPIER_R)
    bmesh.ops.scale(bm, verts=res["verts"], vec=(1.0, 1.0, HOUPPIER_APLAT))
    bmesh.ops.translate(bm, verts=res["verts"],
                        vec=(0, 0, TRONC_H + HOUPPIER_R * HOUPPIER_APLAT * 0.8))
    houppier = {v for v in res["verts"]}
    for face in bm.faces:
        if all(v in houppier for v in face.verts):
            face.smooth = True
    return bm


def maillage_banc():
    bm = bmesh.new()
    cube(bm, (0, 0, 0.42), (1.80, 0.50, 0.08))          # assise
    cube(bm, (0, -0.21, 0.72), (1.80, 0.08, 0.52))      # dossier
    for x in (-0.75, 0.75):                              # pieds
        cube(bm, (x, 0, 0.21), (0.08, 0.44, 0.42))
    return bm


def maillage_velos():
    """Range-velos : trois arceaux en U.

    Premiere version : des arcs en ARETES, sans face. Freestyle ne dessine que
    des surfaces, et les quatorze range-velos etaient purement absents du rendu.
    Des barres en volume, meme grossieres, se voient."""
    bm = bmesh.new()
    for x in (-0.7, 0.0, 0.7):
        for dx in (-0.32, 0.32):
            cube(bm, (x + dx, 0.0, 0.36), (0.06, 0.06, 0.72))
        cube(bm, (x, 0.0, 0.72), (0.70, 0.06, 0.06))
    return bm


def maillage_corbeille():
    bm = bmesh.new()
    cylindre(bm, (0, 0, 0), 0.22, 0.85, segments=6)
    return bm


def maillage_borne():
    bm = bmesh.new()
    cylindre(bm, (0, 0, 0), 0.09, 0.85, segments=6)
    return bm


def maillage_boite():
    bm = bmesh.new()
    cube(bm, (0, 0, 0.75), (0.45, 0.35, 0.70))
    cylindre(bm, (0, 0, 0), 0.08, 0.40, segments=6)
    return bm


def maillage_abri():
    bm = bmesh.new()
    cube(bm, (0, 0, 2.35), (2.60, 1.30, 0.10))          # auvent
    for x in (-1.2, 1.2):
        cube(bm, (x, 0.55, 1.15), (0.10, 0.10, 2.30))
    cube(bm, (0, 0.62, 1.15), (2.60, 0.06, 2.30))       # paroi arriere
    return bm


def maillage_statue():
    """Socle a gradins, piedestal, figure debout.

    La photo fournie par l'auteur donne le detail : Jaures en pierre blanche,
    sur un piedestal de granit a plaque, sur un socle a gradins, au milieu d'une
    nappe d'eau. La nappe appartient au sol, pas a l'objet ; elle viendra avec
    le pavage de la place.
    """
    bm = bmesh.new()
    cube(bm, (0, 0, 0.18), (3.20, 3.20, 0.36))          # gradin bas
    cube(bm, (0, 0, 0.60), (2.20, 2.20, 0.48))          # gradin haut
    cube(bm, (0, 0, 1.90), (1.20, 1.20, 2.10))          # piedestal
    cube(bm, (0, 0, 3.60), (0.52, 0.34, 1.30))          # corps
    cube(bm, (0, 0, 4.42), (0.30, 0.26, 0.34))          # tete
    return bm


FABRIQUES = {
    "arbre": maillage_arbre, "banc": maillage_banc, "velos": maillage_velos,
    "corbeille": maillage_corbeille, "borne": maillage_borne,
    "boite": maillage_boite, "abri": maillage_abri, "statue": maillage_statue,
}


def noeuds_de_la_zone(cfg: dict, scene):
    """Noeuds OSM de la zone portant un genre que l'on sait placer."""
    osm = ROOT / cfg["import"]["source_osm"]
    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    olat, olon = scene.get("lat"), scene.get("lon")
    trouves = []
    for _, el in ET.iterparse(osm, events=("end",)):
        if el.tag != "node":
            continue
        lat, lon = float(el.get("lat")), float(el.get("lon"))
        if not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
            el.clear()
            continue
        tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
        genre = next((g for (k, v), g in GENRES if tags.get(k) == v), None)
        if genre:
            x, y = latlon_to_xy(lat, lon, olat, olon)
            trouves.append((genre, x, y, int(el.get("id"))))
        el.clear()
    return trouves


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_facades.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_mobilier.blend")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene

    # les disques plats de l'import degagent : ils lisent comme des taches
    ancienne = bpy.data.collections.get("vegetation")
    retires = 0
    if ancienne:
        for obj in list(ancienne.objects):
            if obj.name.startswith("tree."):
                bpy.data.objects.remove(obj, do_unlink=True)
                retires += 1
    print(f"[mobilier] {retires} disques d'arbre retires")

    coll = bpy.data.collections.new("mobilier")
    scene.collection.children.link(coll)

    maillages = {}
    for genre, fabrique in FABRIQUES.items():
        bm = fabrique()
        mesh = bpy.data.meshes.new(f"V2_{genre.upper()}")
        bm.to_mesh(mesh)
        bm.free()
        maillages[genre] = mesh

    compte = {}
    for genre, x, y, nid in noeuds_de_la_zone(cfg, scene):
        obj = bpy.data.objects.new(f"{genre}.{nid}", maillages[genre])
        obj.location = (x, y, 0.0)
        coll.objects.link(obj)
        compte[genre] = compte.get(genre, 0) + 1

    total = sum(compte.values())
    for genre, n in sorted(compte.items(), key=lambda kv: -kv[1]):
        print(f"[mobilier] {genre:<10} {n:3d}")
    print(f"[mobilier] {total} objets, {len(maillages)} maillages partages")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[mobilier] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
