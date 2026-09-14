"""Etape 5 — le sol, et le clippage net au bord de la zone.

    blender -b -P v2/05_sol.py

Lit castres_base.blend, ecrit castres_sol.blend. L'etape 2 reste rejouable
seule : on ne modifie jamais le fichier d'import.

DEUX CHOSES, ET ELLES VONT ENSEMBLE.

1. LE CLIPPAGE. Le filtre d'import garde un objet des qu'un seul de ses points
   touche la zone — a dessein, pour ne pas trancher une rangee mitoyenne en
   deux. Mais une rue qui traverse la zone est alors gardee ENTIERE et file a
   des centaines de metres : sur le premier rendu, de longues bandes barraient
   le cadre en diagonale, et quelques batiments flottaient seuls hors du bloc.
   On coupe donc la GEOMETRIE, et non plus les objets, par quatre plans
   verticaux poses sur les bords de la bbox.

2. LE SOL. Sans lui les batiments flottent sur du blanc : rien ne dit ou finit
   la ville. Une dalle a l'emprise exacte de la zone donne au dessin son bord,
   et Freestyle en trace le contour — le losange qui cadre la carte.

L'ordre compte : on clippe d'abord, on pose la dalle ensuite, sinon la dalle se
ferait couper par ses propres plans.
"""
from __future__ import annotations

import argparse
import json
import sys
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

SOL_Z = -0.25          # la dalle passe sous tout le reste
DEBORD_M = 0.0         # la dalle s'arrete exactement au bord de la zone

# EPAISSEUR DES SURFACES DE SOL, en metres. Mesure sur le premier rendu : les
# rues sortaient de l'import a une epaisseur de 0,000 m. Une surface plate posee
# sur une dalle plate n'a ni silhouette ni pli : Freestyle n'a rien a dessiner,
# et la chaussee etait litteralement invisible. Il faut donc lui donner un
# flanc.
#
# Douze centimetres, pas plus : vus a 60 degres et rendus a 25,7 px/m, cela fait
# 3 px de haut. Une ligne, pas un plateau. A un demi-metre la chaussee prendrait
# des allures de quai.
EPAISSEURS = {"streets": 0.12, "open_ground": 0.14, "water": 0.10}


def emprise(cfg: dict, scene) -> tuple[float, float, float, float]:
    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    olat, olon = scene.get("lat"), scene.get("lon")
    if olat is None or olon is None:
        sys.exit("La scene ne porte pas son origine : reprendre a l'etape 2.")
    x0, y0 = latlon_to_xy(lat0, lon0, olat, olon)
    x1, y1 = latlon_to_xy(lat1, lon1, olat, olon)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


PREFIXE_PROFIL = "V2_PROFIL_"


def profil_plat(largeur: float):
    """Segment horizontal servant de profil de balayage a une courbe de rue."""
    nom = f"{PREFIXE_PROFIL}{largeur:.2f}"
    existant = bpy.data.objects.get(nom)
    if existant:
        return existant
    courbe = bpy.data.curves.new(nom, "CURVE")
    courbe.dimensions = "2D"
    spline = courbe.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (-largeur / 2, 0.0, 0.0, 1.0)
    spline.points[1].co = (largeur / 2, 0.0, 0.0, 1.0)
    obj = bpy.data.objects.new(nom, courbe)
    obj.hide_render = True
    bpy.context.scene.collection.objects.link(obj)
    return obj


def elargir_rues(scene) -> tuple[int, int]:
    """Donne sa largeur a chaque courbe de rue, avant toute conversion.

    Sans cela une rue reste un FIL : mesure sur le premier rendu, 39 des 41
    objets de la collection streets n'avaient aucune face, et la chaussee etait
    absente du dessin. La largeur vit dans la propriete road_width que
    l'importateur a posee sur chaque objet ; a defaut, 4 m.
    """
    faits = sans = 0
    for obj in list(scene.objects):
        if obj.type != "CURVE":
            continue
        largeur = obj.get("road_width")
        if largeur is None:
            sans += 1
            largeur = 4.0
        if obj.data.bevel_object is not None or obj.data.bevel_depth:
            continue
        # La courbe doit etre en 3D : une courbe 2D ne se biseaute pas, et la
        # conversion en maillage rend alors un fil sans face. C'est ce qui
        # laissait 39 rues sur 41 invisibles au rendu.
        obj.data.dimensions = "3D"
        obj.data.bevel_mode = "OBJECT"
        obj.data.bevel_object = profil_plat(float(largeur))
        obj.data.use_fill_caps = False
        faits += 1
    return faits, sans


def en_mesh(obj):
    """Convertit une courbe en maillage : on ne peut pas couper une courbe.

    Le graphe de dependances doit avoir ete reevalue depuis la pose des profils,
    sinon la courbe est convertie telle qu'elle etait AVANT — c'est-a-dire en
    fil sans face. Mesure : 39 rues sur 41 sortaient vides.
    """
    if obj.type != "CURVE":
        return obj
    nom = obj.name
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    nouveau = bpy.data.objects.new(nom, mesh)
    nouveau.matrix_world = obj.matrix_world.copy()
    for coll in obj.users_collection:
        coll.objects.link(nouveau)
    for cle in obj.keys():
        if cle not in {"_RNA_UI"}:
            nouveau[cle] = obj[cle]
    bpy.data.objects.remove(obj, do_unlink=True)
    nouveau.name = nom          # sinon Blender laisse le suffixe .001
    return nouveau


def clipper(scene, boite) -> tuple[int, int]:
    """Coupe toute la geometrie aux quatre bords. Renvoie (coupes, vides)."""
    x0, y0, x1, y1 = boite
    plans = [((x0, 0, 0), (-1, 0, 0)), ((x1, 0, 0), (1, 0, 0)),
             ((0, y0, 0), (0, -1, 0)), ((0, y1, 0), (0, 1, 0))]

    coupes = vides = 0
    # Les courbes-profils sont exclues : les convertir en maillage supprimait
    # l'objet courbe que les rues referencent comme bevel_object, et les rues
    # se retrouvaient sans profil — donc sans face. C'est ce qui laissait 39
    # rues sur 41 invisibles, et cela dependait de l'ordre de la boucle.
    for obj in [o for o in scene.objects
                if o.type in {"MESH", "CURVE"}
                and not o.name.startswith(PREFIXE_PROFIL)]:
        obj = en_mesh(obj)
        if obj.type != "MESH" or not obj.data.vertices:
            continue

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        avant = len(bm.verts)
        mat = obj.matrix_world
        inv = mat.inverted()
        for co, no in plans:
            if not bm.verts:
                break
            # les plans sont en coordonnees MONDE ; l'objet a la sienne
            co_local = inv @ Vector(co)
            no_local = (inv.to_3x3().transposed() @ Vector(no)).normalized()
            bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges)
                                   + list(bm.faces),
                                   plane_co=co_local, plane_no=no_local,
                                   clear_outer=True)
        apres = len(bm.verts)
        if apres == 0:
            bm.free()
            bpy.data.objects.remove(obj, do_unlink=True)
            vides += 1
            continue
        if apres != avant:
            coupes += 1
        bm.to_mesh(obj.data)
        bm.free()
    return coupes, vides


def reboucher(scene, collections=("buildings",)) -> int:
    """Referme les maillages ouverts par la coupe.

    bisect_plane laisse le volume BEANT : au bord de la zone on voyait a
    l'interieur des maisons, et Freestyle dessinait consciencieusement leurs
    faces internes. On rebouche la boucle de bord.
    """
    n = 0
    for coll in collections:
        c = bpy.data.collections.get(coll)
        if c is None:
            continue
        for obj in list(c.objects):
            if obj.type != "MESH" or not obj.data.polygons:
                continue
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bords = [e for e in bm.edges if e.is_boundary]
            if bords:
                bmesh.ops.holes_fill(bm, edges=bords)
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                bm.to_mesh(obj.data)
                n += 1
            bm.free()
    return n


def epaissir(scene, epaisseurs: dict) -> int:
    """Donne un flanc aux surfaces de sol, sinon elles n'ont aucune arete."""
    n = 0
    for coll, ep in epaisseurs.items():
        c = bpy.data.collections.get(coll)
        if c is None or ep <= 0:
            continue
        for obj in list(c.objects):
            if obj.type != "MESH" or not obj.data.polygons:
                continue
            if obj.dimensions.z > 0.01:      # deja un volume, on n'y touche pas
                continue
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            resultat = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
            verts = [g for g in resultat["geom"] if isinstance(g, bmesh.types.BMVert)]
            bmesh.ops.translate(bm, verts=verts, vec=(0.0, 0.0, -ep))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(obj.data)
            bm.free()
            n += 1
    return n


def poser_dalle(scene, boite, debord: float = DEBORD_M):
    """Dalle a l'emprise de la zone : c'est elle qui donne son bord au dessin."""
    x0, y0, x1, y1 = boite
    x0 -= debord
    y0 -= debord
    x1 += debord
    y1 += debord

    mesh = bpy.data.meshes.new("V2_SOL")
    bm = bmesh.new()
    coins = [bm.verts.new((x, y, SOL_Z))
             for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    bm.faces.new(coins)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("V2_SOL", mesh)
    scene.collection.objects.link(obj)
    obj["surface"] = "sol"
    return obj, (x1 - x0, y1 - y0)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_base.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_sol.blend")
    p.add_argument("--sans-dalle", action="store_true")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    boite = emprise(cfg, scene)
    print(f"[sol] zone : x {boite[0]:.0f}..{boite[2]:.0f}  y {boite[1]:.0f}..{boite[3]:.0f}"
          f"  ({boite[2]-boite[0]:.0f} x {boite[3]-boite[1]:.0f} m)")

    faits, sans = elargir_rues(scene)
    bpy.context.view_layer.update()      # sans quoi la conversion voit l'etat d'avant
    print(f"[sol] {faits} courbes elargies ({sans} sans road_width, 4 m par defaut)")

    avant = len(scene.objects)
    coupes, vides = clipper(scene, boite)
    print(f"[sol] clippage : {coupes} objets coupes, {vides} entierement hors zone "
          f"supprimes, {len(scene.objects)}/{avant} restants")

    for obj in [o for o in list(scene.objects) if o.name.startswith(PREFIXE_PROFIL)]:
        bpy.data.objects.remove(obj, do_unlink=True)

    n = reboucher(scene)
    print(f"[sol] {n} volumes rebouches apres la coupe")
    n = epaissir(scene, EPAISSEURS)
    print(f"[sol] {n} surfaces de sol epaissies "
          + ", ".join(f"{k} {v*100:.0f} cm" for k, v in EPAISSEURS.items()))

    if not args.sans_dalle:
        _, taille = poser_dalle(scene, boite)
        print(f"[sol] dalle posee : {taille[0]:.0f} x {taille[1]:.0f} m a z={SOL_Z}")

    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[sol] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
