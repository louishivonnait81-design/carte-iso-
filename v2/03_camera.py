"""Etape 3 — camera isometrique et style ligne claire.

    blender -b -P v2/03_camera.py -- --z 45 --largeur 2000 --sortie test.png

Importable : 04_previews.py appelle `preparer()` puis `rendre()` pour chaque
orientation, sans rouvrir le fichier a chaque fois.

DEUX POINTS TECHNIQUES QUI CONTREDISENT LE BRIEF, et il vaut mieux le dire ici
que le decouvrir sur un rendu vide.

1. FREESTYLE NE FONCTIONNE PAS AVEC WORKBENCH. Workbench est un moteur d'apercu
   de fenetre ; il ne passe pas par le pipeline de post-traitement ou vit
   Freestyle. Seuls Cycles et EEVEE le rendent. Le brief demandant Freestyle et
   interdisant Cycles, il ne reste qu'EEVEE. config.json est corrige en
   consequence.

2. LE CADRAGE EST CALCULE, PAS ESTIME. On projette les huit coins de la boite
   englobante de chaque objet dans le repere ecran de la camera — les huit
   coins, pas le centre au sol : en vue plongeante la hauteur decale un batiment
   vers le haut de l'image, et un cadrage calcule au sol couperait les toits.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy

V2 = Path(__file__).resolve().parent
ROOT = V2.parent
CONFIG = V2 / "config.json"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from geo import CameraBasis, latlon_to_xy, project  # noqa: E402


def materiau_blanc() -> bpy.types.Material:
    """Blanc pur, emissif : aucune ombre, aucun degrade, quel que soit l'eclairage."""
    mat = bpy.data.materials.get("V2_BLANC") or bpy.data.materials.new("V2_BLANC")
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs[1].default_value = 1.0
    sortie = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emission.outputs[0], sortie.inputs[0])
    return mat


def aplatir_materiaux(scene) -> int:
    mat = materiau_blanc()
    n = 0
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        n += 1
    return n


def monde_blanc(scene) -> None:
    monde = scene.world or bpy.data.worlds.new("V2_MONDE")
    scene.world = monde
    monde.use_nodes = True
    fond = monde.node_tree.nodes.get("Background")
    if fond:
        fond.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
        fond.inputs[1].default_value = 1.0


def boite_ecran(scene, basis: CameraBasis, cible):
    """Boite englobante de la scene dans le repere ecran, en metres."""
    from mathutils import Vector

    us, vs = [], []
    for obj in scene.objects:
        if obj.type not in {"MESH", "CURVE"}:
            continue
        for coin in obj.bound_box:
            p = obj.matrix_world @ Vector(coin)
            u, v = project((p.x, p.y, p.z), cible, basis)
            us.append(u)
            vs.append(v)
    if not us:
        sys.exit("Scene vide : rien a cadrer.")
    return min(us), min(vs), max(us), max(vs)


def centre_scene(scene):
    from mathutils import Vector

    pts = []
    for obj in scene.objects:
        if obj.type not in {"MESH", "CURVE"}:
            continue
        for coin in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(coin))
    if not pts:
        return (0.0, 0.0, 0.0)
    return (sum(p.x for p in pts) / len(pts),
            sum(p.y for p in pts) / len(pts),
            sum(p.z for p in pts) / len(pts))


def coins_bbox(cfg: dict, scene, origine):
    """Les huit coins du prisme de la zone : l'emprise au sol x la hauteur batie.

    On cadre sur LA ZONE, pas sur les objets. Le filtre d'import garde un objet
    des qu'un seul de ses points touche la boite, pour ne pas trancher une
    rangee en deux — mais une rue qui traverse la zone est alors gardee ENTIERE
    et file a des centaines de metres. Mesure : cadrer sur les objets donnait
    1820 m de large la ou la bbox en demande 1100. Ces rues debordantes seront
    simplement coupees par le cadre, ce qui est le comportement voulu.
    """
    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    olat, olon = origine
    x0, y0 = latlon_to_xy(lat0, lon0, olat, olon)
    x1, y1 = latlon_to_xy(lat1, lon1, olat, olon)
    hauts = [obj.matrix_world.translation.z + obj.dimensions.z
             for obj in scene.objects if obj.type == "MESH"]
    zmax = max(hauts) if hauts else 0.0
    return [(x, y, z) for x in (min(x0, x1), max(x0, x1))
            for y in (min(y0, y1), max(y0, y1)) for z in (0.0, zmax)]


def poser_camera(scene, cfg: dict, z_deg: float, distance: float = 4000.0):
    """Camera ortho, cadree sur la zone definie par la bbox."""
    rx = cfg["camera"]["rotation_x_deg"]
    basis = CameraBasis.from_angles(elevation_deg=90.0 - rx, azimuth_deg=z_deg)
    origine = (scene.get("lat"), scene.get("lon"))
    coins = (coins_bbox(cfg, scene, origine)
             if cfg["zone"]["bbox"] and None not in origine else None)
    cible = (sum(c[0] for c in coins) / len(coins),
             sum(c[1] for c in coins) / len(coins), 0.0) if coins else centre_scene(scene)

    data = bpy.data.cameras.get("V2_CAM") or bpy.data.cameras.new("V2_CAM")
    cam = bpy.data.objects.get("V2_CAM")
    if cam is None:
        cam = bpy.data.objects.new("V2_CAM", data)
        scene.collection.objects.link(cam)
    cam.data = data
    data.type = cfg["camera"]["type"]
    data.clip_start = 1.0
    data.clip_end = distance * 4.0
    data.shift_x = data.shift_y = 0.0

    if coins:
        us = [project(c, cible, basis)[0] for c in coins]
        vs = [project(c, cible, basis)[1] for c in coins]
        umin, vmin, umax, vmax = min(us), min(vs), max(us), max(vs)
    else:
        umin, vmin, umax, vmax = boite_ecran(scene, basis, cible)
    uc, vc = (umin + umax) / 2.0, (vmin + vmax) / 2.0
    marge = cfg["camera"]["marge_cadrage"]
    data.ortho_scale = max(umax - umin, vmax - vmin) * marge

    centre = tuple(cible[i] + uc * basis.right[i] + vc * basis.up[i] for i in range(3))
    cam.location = tuple(centre[i] - basis.view[i] * distance for i in range(3))
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = (math.radians(rx), 0.0, math.radians(z_deg))
    scene.camera = cam
    return cam, (umax - umin, vmax - vmin)


def poser_freestyle(scene, cfg: dict, moteur: str | None = None) -> None:
    # EEVEE est le choix par defaut, celui du Mac. En rendu LOGICIEL il est
    # inutilisable : mesure dans le conteneur, 86 s pour 600 px. Sur cette scene
    # plate et emissive, Cycles CPU est environ vingt fois plus rapide, d'ou le
    # parametre. Workbench, lui, n'est pas une option : il ne rend pas Freestyle.
    scene.render.engine = moteur or cfg["rendu"]["moteur"]
    if scene.render.engine == "CYCLES":
        scene.cycles.device = "CPU"
        scene.cycles.samples = 4          # aplat emissif : quelques rayons suffisent
        scene.cycles.use_denoising = False
        scene.cycles.max_bounces = 0
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"
    scene.render.line_thickness = cfg["rendu"]["epaisseur_trait_px"]

    vue = scene.view_layers[0]
    vue.use_freestyle = True
    for jeu in list(vue.freestyle_settings.linesets):
        vue.freestyle_settings.linesets.remove(jeu)
    jeu = vue.freestyle_settings.linesets.new("V2_LIGNES")
    jeu.select_silhouette = True
    jeu.select_border = True
    jeu.select_crease = True
    jeu.select_contour = True
    jeu.select_external_contour = True
    jeu.linestyle.color = (0.0, 0.0, 0.0)
    jeu.linestyle.thickness = cfg["rendu"]["epaisseur_trait_px"]

    # le blanc doit rester blanc pur : aucune transformation de vue
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0


def preparer(cfg: dict, moteur: str | None = None):
    scene = bpy.context.scene
    monde_blanc(scene)
    n = aplatir_materiaux(scene)
    poser_freestyle(scene, cfg, moteur)
    return scene, n


def rendre(scene, cfg: dict, z_deg: float, largeur: int, sortie: Path):
    cam, taille = poser_camera(scene, cfg, z_deg)
    hauteur = largeur                      # la camera est cadree au carre
    r = scene.render
    r.resolution_x, r.resolution_y = largeur, hauteur
    r.resolution_percentage = 100
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.filepath = str(sortie)
    bpy.ops.render.render(write_still=True)
    return taille


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_base.blend")
    p.add_argument("--z", type=float, default=None)
    p.add_argument("--largeur", type=int, default=None)
    p.add_argument("--sortie", type=Path, default=V2 / "test.png")
    p.add_argument("--moteur", default=None,
                   help="BLENDER_EEVEE (defaut) ou CYCLES")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene, n = preparer(cfg, args.moteur)
    z = args.z if args.z is not None else cfg["camera"]["rotation_z_deg"]
    largeur = args.largeur or cfg["rendu"]["largeur_test_px"]
    print(f"[camera] {n} objets en blanc plat, X={cfg['camera']['rotation_x_deg']}, Z={z}")
    w, h = rendre(scene, cfg, z, largeur, args.sortie)
    print(f"[camera] scene cadree : {w:.0f} m x {h:.0f} m a l'ecran")
    print(f"[camera] -> {args.sortie}  {largeur}x{largeur}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
