"""Du squelette GeoJSON au dessin : volumes, camera isometrique, trait.

    blender -b -P build_blender.py -- blocks.geojson out/ 4000

Le dernier nombre est la largeur du rendu en pixels : 4000 pour regarder,
13000 pour 110 cm a 300 dpi. Sorties dans `out/` : castres.png, castres.svg
(ouvrable dans Inkscape) et castres.blend (pour inspecter).

Les trois reglages qui changent le dessin sont en tete de fichier.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

# --------------------------------------------------------------- les reglages
ISO_TURN = 315          # quart de tour de la carte : 45, 135, 225 ou 315
ISO_ELEVATION = 41      # degres au-dessus de l'horizon
LINE_THICKNESS = 1.5    # px, pour LINE_REF_WIDTH
LINE_REF_WIDTH = 8000   # largeur pour laquelle l'epaisseur ci-dessus est ecrite
MARGE_CADRAGE = 1.02

# ISO_ELEVATION vaut 41 parce que c'est la valeur MESUREE sur une planche
# MicroMacro : les deux bords d'une meme toiture y tombent a +14 et -61 degres
# sur la page, et pour une projection orthographique
# |tan(a1) x tan(a2)| = sin^2(elevation), independamment de l'orientation du
# batiment. Voir v2/mesure_reference.py, qui rejoue le controle.
#
# LINE_THICKNESS suit la resolution. Freestyle compte en PIXELS ABSOLUS : sans
# cette mise a l'echelle, le meme reglage donne un dessin differemment charge a
# 4000 et a 13000 px, et tout apercu ment. A cette valeur, le rendu retrouve le
# profil d'epaisseur de la reference : p25=2 p50=2 p75=3 p90=4 pixels.

PENTE = 0.53            # un versant de tuile canal : environ 28 degres
MONTEE_MAX = 3.2        # m
PART_MONTEE_MAX = 0.45  # la toiture ne depasse jamais cette part du mur
ACROTERE = 0.35
EPAISSEUR_SOL = {"square": 0.10, "green": 0.12, "water": 0.08}
Z_DALLE = -0.25


# --------------------------------------------------------------- la geometrie
def anneaux(geometrie):
    """Contours exterieurs d'une geometrie GeoJSON, en listes de (x, y)."""
    t = geometrie["type"]
    if t == "Polygon":
        return [geometrie["coordinates"][0]]
    if t == "MultiPolygon":
        return [p[0] for p in geometrie["coordinates"]]
    return []


def face_depuis_contour(bm, contour, z=0.0):
    """Cree une face a partir d'un contour ferme, sans supposer qu'il est convexe.

    On pose les aretes puis on laisse bmesh fabriquer la face : un `create_face`
    naif sur un contour en L se replie.
    """
    pts = list(contour)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return None
    verts = [bm.verts.new((float(x), float(y), z)) for x, y in pts]
    for a, b in zip(verts, verts[1:] + verts[:1]):
        if not bm.edges.get((a, b)):
            bm.edges.new((a, b))
    res = bmesh.ops.contextual_create(bm, geom=verts + list(bm.edges))
    faces = [f for f in res["faces"] if f.is_valid]
    if not faces:
        return None
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def axe_long(pts):
    """Direction dominante d'un contour, par analyse en composantes."""
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    cxx = sum((p[0] - mx) ** 2 for p in pts) / n
    cyy = sum((p[1] - my) ** 2 for p in pts) / n
    cxy = sum((p[0] - mx) * (p[1] - my) for p in pts) / n
    a = 0.5 * math.atan2(2 * cxy, cxx - cyy)
    return Vector((math.cos(a), math.sin(a), 0.0)), Vector((mx, my, 0.0))


def faitage(bm, dessus, contour, zmax, petit, montee) -> bool:
    """Coupe la face du dessus le long de l'axe long et remonte le faitage."""
    axe, centre = axe_long(contour)
    normale = Vector((-axe.y, axe.x, 0.0))
    geom = set(dessus)
    for f in dessus:
        geom.update(f.verts)
        geom.update(f.edges)
    bmesh.ops.bisect_plane(bm, geom=list(geom), dist=1e-4,
                           plane_co=(centre.x, centre.y, zmax),
                           plane_no=tuple(normale))
    hauts = [v for v in bm.verts if abs(v.co.z - zmax) < 1e-3]
    if not hauts:
        return False
    demi = petit / 2.0
    for v in hauts:
        d = abs((v.co - Vector((centre.x, centre.y, zmax))).dot(normale))
        v.co.z += montee * max(0.0, 1.0 - d / demi)
    return True


def poser_toit(bm, dessus, contour, hauteur, genre):
    """Deux pans, une croupe, ou un acrotere. Renvoie le genre effectivement pose.

    Le faitage ne CONSTRUIT rien : on coupe la face du dessus le long de l'axe
    long et chaque sommet remonte selon sa distance a cet axe. Un angle rentrant
    ne peut donc pas replier l'inset, puisqu'il n'y a pas d'inset — c'est ce qui
    faisait degenerer les toits sur les emprises en L.
    """
    if not dessus:
        return "aucune"
    zmax = max(v.co.z for f in dessus for v in f.verts)
    xs = [p[0] for p in contour]
    ys = [p[1] for p in contour]
    petit = min(max(xs) - min(xs), max(ys) - min(ys))
    montee = min(MONTEE_MAX, PENTE * petit / 2, PART_MONTEE_MAX * hauteur)

    if genre == "gable" and petit >= 3.0:
        if faitage(bm, dessus, contour, zmax, petit, montee):
            return "gable"

    if genre == "hip" and petit >= 4.0:
        avant = [(min(xs), min(ys)), (max(xs), max(ys))]
        bmesh.ops.inset_region(bm, faces=dessus, thickness=0.42 * petit,
                               depth=montee, use_even_offset=True,
                               use_boundary=True)
        # l'offset "even" divise par sin(angle/2) : sur une pointe il envoie un
        # sommet a l'autre bout de la carte. On ne le prevoit pas, on le
        # constate, et on retombe sur l'acrotere.
        deborde = max(max(avant[0][0] - v.co.x, v.co.x - avant[1][0],
                          avant[0][1] - v.co.y, v.co.y - avant[1][1])
                      for v in bm.verts)
        if deborde <= 0.5:
            return "hip"
        # l'inset s'est replie. Un faitage, lui, ne deplace aucun sommet dans le
        # plan : c'est le repli le plus sur. Sans cela, 106 volumes sur 133
        # finissaient en toit-terrasse — un centre ancien tout en terrasses.
        bm.clear()
        faces = face_depuis_contour(bm, contour, 0.0)
        if faces:
            haut = bmesh.ops.extrude_face_region(bm, geom=faces)
            verts = [g for g in haut["geom"] if isinstance(g, bmesh.types.BMVert)]
            bmesh.ops.translate(bm, verts=verts, vec=(0, 0, hauteur))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            dessus = [f for f in bm.faces if f.normal.z > 0.9
                      and abs(f.calc_center_median().z - hauteur) < 0.05]
            if dessus and petit >= 3.0 and faitage(bm, dessus, contour,
                                                   hauteur, petit, montee):
                return "gable"

    dessus = [f for f in bm.faces if f.normal.z > 0.9
              and abs(f.calc_center_median().z - zmax) < 0.05]
    if dessus:
        res = bmesh.ops.inset_region(bm, faces=dessus, thickness=0.30, depth=0.0,
                                     use_even_offset=False, use_boundary=True)
        pourtour = set(res["faces"])
        interieur = [f for f in dessus if f.is_valid and f not in pourtour]
        verts = {v for f in interieur for v in f.verts}
        if verts:
            bmesh.ops.translate(bm, verts=list(verts), vec=(0, 0, -ACROTERE))
    return "flat"


def batir_volume(nom, contour, hauteur, genre, collection):
    bm = bmesh.new()
    faces = face_depuis_contour(bm, contour, 0.0)
    if not faces:
        bm.free()
        return None
    haut = bmesh.ops.extrude_face_region(bm, geom=faces)
    verts = [g for g in haut["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=verts, vec=(0, 0, hauteur))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    dessus = [f for f in bm.faces if f.normal.z > 0.9
              and abs(f.calc_center_median().z - hauteur) < 0.05]
    pose = poser_toit(bm, dessus, contour, hauteur, genre)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(nom)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(nom, mesh)
    collection.objects.link(obj)
    return pose


def batir_nappe(nom, contour, epaisseur, collection):
    bm = bmesh.new()
    faces = face_depuis_contour(bm, contour, 0.0)
    if not faces:
        bm.free()
        return False
    haut = bmesh.ops.extrude_face_region(bm, geom=faces)
    verts = [g for g in haut["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=verts, vec=(0, 0, epaisseur))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(nom)
    bm.to_mesh(mesh)
    bm.free()
    collection.objects.link(bpy.data.objects.new(nom, mesh))
    return True


def dalle(boite, collection):
    x0, y0, x1, y1 = boite
    bm = bmesh.new()
    coins = [bm.verts.new((x, y, Z_DALLE))
             for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    bm.faces.new(coins)
    mesh = bpy.data.meshes.new("SOL")
    bm.to_mesh(mesh)
    bm.free()
    collection.objects.link(bpy.data.objects.new("SOL", mesh))


# ------------------------------------------------------------------ la camera
def poser_camera(scene, boite, hauteur_max):
    x0, y0, x1, y1 = boite
    cam_data = bpy.data.cameras.new("CAM")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("CAM", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    rot_x = math.radians(90 - ISO_ELEVATION)
    rot_z = math.radians(ISO_TURN)
    cam.rotation_euler = (rot_x, 0.0, rot_z)
    centre = Vector(((x0 + x1) / 2, (y0 + y1) / 2, hauteur_max / 2))
    direction = Vector((math.sin(rot_z) * math.sin(rot_x),
                        -math.cos(rot_z) * math.sin(rot_x),
                        math.cos(rot_x)))
    diagonale = math.dist((x0, y0), (x1, y1)) + hauteur_max
    cam.location = centre + direction * diagonale

    droite = Vector((math.cos(rot_z), math.sin(rot_z), 0.0))
    haut = Vector((-math.sin(rot_z) * math.cos(rot_x),
                   math.cos(rot_z) * math.cos(rot_x), math.sin(rot_x)))
    us, vs = [], []
    for x in (x0, x1):
        for y in (y0, y1):
            for z in (0.0, hauteur_max):
                p = Vector((x, y, z)) - centre
                us.append(p.dot(droite))
                vs.append(p.dot(haut))
    largeur_m = (max(us) - min(us)) * MARGE_CADRAGE
    hauteur_m = (max(vs) - min(vs)) * MARGE_CADRAGE
    cam_data.ortho_scale = max(largeur_m, hauteur_m)
    cam_data.clip_end = diagonale * 3
    return largeur_m, hauteur_m


def poser_freestyle(scene, largeur_px):
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"
    k = largeur_px / float(LINE_REF_WIDTH)
    scene.render.line_thickness = LINE_THICKNESS * k
    vue = scene.view_layers[0]
    vue.use_freestyle = True
    reglages = vue.freestyle_settings
    for jeu in list(reglages.linesets):
        reglages.linesets.remove(jeu)

    def ligne(nom, epaisseur, **drapeaux):
        jeu = reglages.linesets.new(nom)
        for cle in ("select_silhouette", "select_border", "select_crease",
                    "select_contour", "select_external_contour",
                    "select_edge_mark"):
            setattr(jeu, cle, drapeaux.get(cle, False))
        jeu.linestyle.color = (0.0, 0.0, 0.0)
        jeu.linestyle.thickness = epaisseur * k
        return jeu

    ligne("MASSES", LINE_THICKNESS, select_silhouette=True, select_border=True,
          select_contour=True, select_external_contour=True)
    ligne("PLIS", LINE_THICKNESS * 0.67, select_crease=True)


def blanc_plat(scene):
    """Tout en blanc emissif : le dessin ne doit rien au relief lumineux."""
    mat = bpy.data.materials.new("BLANC")
    mat.use_nodes = True
    arbre = mat.node_tree
    for n in list(arbre.nodes):
        arbre.nodes.remove(n)
    sortie = arbre.nodes.new("ShaderNodeOutputMaterial")
    emission = arbre.nodes.new("ShaderNodeEmission")
    emission.inputs[0].default_value = (1, 1, 1, 1)
    arbre.links.new(emission.outputs[0], sortie.inputs[0])
    n = 0
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        n += 1
    monde = bpy.data.worlds.new("FOND")
    monde.use_nodes = True
    monde.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    scene.world = monde
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    return n


def exporter_svg(scene, dossier: Path) -> bool:
    """Le SVG passe par l'extension Freestyle SVG Exporter, livree avec Blender.

    Elle N'EST PAS dans le module pip `bpy`. Sur un Blender d'application elle
    s'active ici meme ; ailleurs on le dit et on rend quand meme le PNG.
    """
    try:
        bpy.ops.preferences.addon_enable(module="render_freestyle_svg")
    except Exception as erreur:                      # noqa: BLE001
        print(f"[build] pas de SVG : {erreur}")
        return False
    reglages = getattr(scene, "svg_export", None)
    if reglages is None:
        print("[build] pas de SVG : l'extension n'expose pas svg_export")
        return False
    reglages.use_svg_export = True
    reglages.mode = "FRAME"
    reglages.split_at_invisible = True
    return True


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 2:
        sys.exit("usage : blender -b -P build_blender.py -- blocks.geojson out/ [largeur]")
    source = Path(argv[0])
    dossier = Path(argv[1])
    largeur_px = int(argv[2]) if len(argv) > 2 else 4000
    dossier.mkdir(parents=True, exist_ok=True)

    donnees = json.loads(source.read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    familles = {}
    for genre in ("volumes", "reperes", "sol"):
        coll = bpy.data.collections.new(genre)
        scene.collection.children.link(coll)
        familles[genre] = coll

    compte, toits = {}, {}
    xs, ys, hmax = [], [], 1.0
    for i, f in enumerate(donnees["features"]):
        props = f["properties"]
        genre = props.get("kind")
        for contour in anneaux(f["geometry"]):
            xs += [p[0] for p in contour]
            ys += [p[1] for p in contour]
            if genre in ("volume", "landmark"):
                h = float(props.get("height", 6.0))
                hmax = max(hmax, h)
                pose = batir_volume(f"{genre}.{i:04d}", contour, h,
                                    props.get("roof", "hip"),
                                    familles["reperes" if genre == "landmark"
                                             else "volumes"])
                if pose:
                    toits[pose] = toits.get(pose, 0) + 1
            elif genre in EPAISSEUR_SOL:
                batir_nappe(f"{genre}.{i:04d}", contour,
                            EPAISSEUR_SOL[genre], familles["sol"])
        compte[genre] = compte.get(genre, 0) + 1

    boite = (min(xs), min(ys), max(xs), max(ys))
    dalle(boite, familles["sol"])
    for genre, n in sorted(compte.items(), key=lambda kv: -kv[1]):
        print(f"[build] {genre:<10} {n:4d}")
    print("[build] toitures : " + ", ".join(f"{k} {v}" for k, v in sorted(toits.items())))

    n = blanc_plat(scene)
    largeur_m, hauteur_m = poser_camera(scene, boite, hmax)
    poser_freestyle(scene, largeur_px)

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 4
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 0
    hauteur_px = max(1, int(round(largeur_px * hauteur_m / largeur_m)))
    r = scene.render
    r.resolution_x, r.resolution_y = largeur_px, hauteur_px
    r.resolution_percentage = 100
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.filepath = str(dossier / "castres.png")

    svg = exporter_svg(scene, dossier)
    print(f"[build] {n} objets, cadrage {largeur_m:.0f} x {hauteur_m:.0f} m, "
          f"{largeur_px}x{hauteur_px} px, tour {ISO_TURN} deg, "
          f"elevation {ISO_ELEVATION} deg")
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(dossier / "castres.blend"))
    print(f"[build] -> {dossier / 'castres.png'}"
          + (f", {dossier / 'castres.svg'}" if svg else " (pas de SVG ici)")
          + f", {dossier / 'castres.blend'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
