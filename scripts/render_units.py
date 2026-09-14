"""Rend chaque UNITE DE DESSIN seule, avec sa boite de collage au pixel pres.

    blender --background --python scripts/render_units.py -- --only tile_1_4

Pourquoi. Le modele ne place pas la matiere ou on le lui dit : sur le meilleur
rendu de tuile obtenu, 34,8 % de l'encre tombait hors de toute emprise batie,
dont deux maisons entieres posees en pleine place. On ne lui demande donc plus
de la placer. Chaque unite — une rangee mitoyenne, cf. scripts/units.py — est
rendue seule sur fond blanc, redessinee seule, et recollee par le compositeur a
la position que ce script a mesuree. La derive de position cesse d'etre une
propriete du dessin pour devenir une propriete du code.

Trois fichiers par unite :

    <nom>_line.png   le squelette Freestyle de l'unite, seule, sur blanc
    <nom>_mask.png   sa silhouette pleine, blanche sur noir
    index.json       la boite de collage, en pixels de la mosaique

Le masque n'est pas un luxe. En vue isometrique une rangee proche cache une
rangee lointaine ; colle sans masque, le dessin d'arriere-plan transparaitrait
au travers des murs du premier plan. Le compositeur colle donc d'arriere en
avant, chaque unite decoupee par sa silhouette.

Le cadrage de chaque unite est calcule, pas devine : on projette les sommets
reels de ses objets dans le repere ecran de la camera de la mosaique, ce qui
donne sa boite en metres, donc en pixels. La camera est ensuite recentree sur
cette boite. Aucun recadrage a posteriori, aucune recherche de correspondance.
"""
from __future__ import annotations

import bpy  # noqa: F401  (doit preceder les autres imports Blender)

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import iso_tiles  # noqa: E402
import osm_to_blend as ob  # noqa: E402
from geo import TileGrid, latlon_to_xy, project  # noqa: E402
from units import Building, boxes_touching, build_units  # noqa: E402

# Marge autour d'une unite, en metres. Elle laisse respirer le trait epais du
# contour et evite qu'un debord de toit soit coupe au ras du cadre.
MARGIN_M = 2.0


# --------------------------------------------------------------------------
# Geometrie : de l'unite a sa boite ecran
# --------------------------------------------------------------------------

def screen_bbox(objects, grid: TileGrid) -> tuple[float, float, float, float]:
    """Boite englobante d'objets Blender dans le repere ecran, en metres.

    On projette les huit coins de la boite englobante monde de chaque objet, et
    non son centre : en isometrique la hauteur decale un batiment vers le haut
    de l'image, et un cadrage calcule au sol couperait les toits.
    """
    us, vs = [], []
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ __import__("mathutils").Vector(corner)
            u, v = project((world.x, world.y, world.z), grid.target, grid.basis)
            us.append(u)
            vs.append(v)
    return min(us), min(vs), max(us), max(vs)


def depth_key(objects, grid: TileGrid) -> float:
    """Profondeur de l'unite le long de l'axe de visee.

    Le compositeur peint d'arriere en avant : la cle la plus grande est la plus
    eloignee de la camera, donc la premiere posee.
    """
    view = grid.basis.view
    best = -math.inf
    for obj in objects:
        for corner in obj.bound_box:
            w = obj.matrix_world @ __import__("mathutils").Vector(corner)
            d = w.x * view[0] + w.y * view[1] + w.z * view[2]
            best = max(best, d)
    return -best


def mosaic_box(bbox_m: tuple[float, float, float, float],
               grid: TileGrid) -> tuple[int, int, int, int]:
    """Boite ecran en metres -> boite en pixels de la mosaique (x, y, w, h).

    L'origine pixel est le coin haut-gauche de la mosaique, y vers le bas,
    comme dans toute image.
    """
    umin, vmin, umax, vmax = bbox_m
    ppm = grid.tile_px / grid.tile_m
    half_w = grid.cols * grid.tile_m / 2.0
    half_h = grid.rows * grid.tile_m / 2.0
    x0 = (umin + half_w) * ppm
    x1 = (umax + half_w) * ppm
    y0 = (half_h - vmax) * ppm          # vmax est en HAUT de l'image
    y1 = (half_h - vmin) * ppm
    x, y = int(round(x0)), int(round(y0))
    return x, y, int(round(x1)) - x, int(round(y1)) - y


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------

def aim_camera(cam, grid: TileGrid, bbox_m, distance: float) -> None:
    """Recentre la camera orthographique sur la boite, sans changer son axe."""
    umin, vmin, umax, vmax = bbox_m
    uc, vc = (umin + umax) / 2.0, (vmin + vmax) / 2.0
    right, up, view = grid.basis.right, grid.basis.up, grid.basis.view
    target = grid.target
    centre = tuple(target[i] + uc * right[i] + vc * up[i] for i in range(3))
    cam.location = tuple(centre[i] - view[i] * distance for i in range(3))
    cam.data.ortho_scale = max(umax - umin, vmax - vmin)


def only_visible(scene, keep: set[str]) -> None:
    """Ne laisse dans le rendu que les objets nommes dans `keep`."""
    for obj in scene.objects:
        if obj.type == "CAMERA":
            continue
        hide = obj.name not in keep
        obj.hide_render = hide
        obj.hide_viewport = hide


def render_to(scene, path: Path, width: int, height: int) -> None:
    scene.render.resolution_x = max(1, width)
    scene.render.resolution_y = max(1, height)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def setup_mask_pass(scene) -> None:
    """Silhouette pleine : Workbench a plat, objets blancs sur fond noir.

    Freestyle est desactive ici — on veut la surface, pas son contour.
    """
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "SINGLE"
    shading.single_color = (1.0, 1.0, 1.0)
    shading.show_object_outline = False
    scene.render.use_freestyle = False
    scene.render.film_transparent = False
    world = scene.world
    if world is not None:
        world.use_nodes = False
        world.color = (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------

def load_units(osm_path: Path, grid: TileGrid, max_extent: float):
    osm = ob.Osm.parse(osm_path)
    lat0, lon0 = grid.origin_lat, grid.origin_lon
    buildings = {}
    for wid, tags in osm.way_tags.items():
        if ob.category_of(tags) != "building":
            continue
        nodes = osm.ways[wid]
        pts = []
        for nid in nodes:
            p = osm.nodes.get(nid)
            if p:
                pts.append(latlon_to_xy(p[0], p[1], lat0, lon0))
        if len(pts) < 3:
            continue
        buildings[wid] = Building(wid, pts, tags, nodes)
    return build_units(buildings, max_extent)



def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=ROOT / "assets" / "castres.blend")
    p.add_argument("--osm", type=Path, default=ROOT / "assets" / "castres.osm")
    p.add_argument("--out", type=Path, default=ROOT / "units")
    p.add_argument("--only", default=None,
                   help="ne rendre que les unites touchant cette tuile, ex. tile_1_4")
    p.add_argument("--units", default=None, help="unites precises, ex. 'u83180530,u83180844'")
    p.add_argument("--rows", type=int, default=4)
    p.add_argument("--cols", type=int, default=7)
    p.add_argument("--tile", type=float, default=60.0)
    p.add_argument("--px", type=int, default=2048)
    p.add_argument("--center-latlon", type=float, nargs=2, default=(43.60482, 2.24177))
    p.add_argument("--origin-latlon", type=float, nargs=2, default=None,
                   help="origine du monde Blender ; par defaut celle ecrite dans la scene")
    p.add_argument("--elevation", type=float, default=45.0)
    p.add_argument("--azimuth", type=float, default=45.0)
    p.add_argument("--max-extent", type=float, default=45.0)
    p.add_argument("--margin", type=float, default=MARGIN_M)
    p.add_argument("--line-thickness", type=float, default=2.6)
    p.add_argument("--samples", type=int, default=8)
    p.add_argument("--camera-distance", type=float, default=2000.0)
    p.add_argument("--force", action="store_true")
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    return p.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv)
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene

    lat, lon = args.center_latlon
    # L'ORIGINE DU MONDE BLENDER N'EST PAS LE CENTRE DE LA GRILLE. La scene est
    # construite autour de son propre point de reference, ecrit dans
    # scene["lat"]/["lon"] ; ici (43,60525 ; 2,2410), soit le centre de la grille
    # decale de 62 m en x et de -48 m en y. Batir la grille avec le centre comme
    # origine decalait donc chaque unite d'autant, et le controle de chainage est
    # tombe a 5 % de concordance. On lit l'origine dans la scene, comme le fait
    # iso_tiles pour les tuiles : les deux repartent ainsi du meme point.
    olat, olon = iso_tiles.scene_origin(
        scene, tuple(args.origin_latlon) if args.origin_latlon else None)
    grid = TileGrid.build(args.rows, args.cols, args.tile, args.px, lat, lon, olat, olon,
                          elevation_deg=args.elevation, azimuth_deg=args.azimuth)
    print(f"[unites] origine de la scene : {olat}, {olon}")

    units = load_units(args.osm, grid, args.max_extent)
    if args.units:
        wanted = set(args.units.split(","))
        units = [u for u in units if u.name in wanted]

    args.out.mkdir(parents=True, exist_ok=True)
    cam = iso_tiles.setup_camera(scene, grid, args.camera_distance)
    iso_tiles.setup_output(scene, args.px)

    # Les noms OSM voyagent avec l'index : c'est par eux que le prompt d'une
    # unite retrouve la fiche du lieu qu'elle porte.
    named = {}
    for wid, tags in ob.Osm.parse(args.osm).way_tags.items():
        if tags.get("name") and ob.category_of(tags) == "building":
            named[str(wid)] = tags["name"]

    index = {"grid": {"rows": args.rows, "cols": args.cols, "tile_m": args.tile,
                      "tile_px": args.px, "elevation": args.elevation,
                      "azimuth": args.azimuth,
                      "mosaic_px": list(grid.mosaic_px)},
             "names": named,
             "units": []}

    records = []
    for unit in units:
        names = {f"building.{w}" for w in unit.way_ids}
        objects = [bpy.data.objects[n] for n in names if n in bpy.data.objects]
        if not objects:
            continue
        umin, vmin, umax, vmax = screen_bbox(objects, grid)
        bbox = (umin - args.margin, vmin - args.margin,
                umax + args.margin, vmax + args.margin)
        x, y, w, h = mosaic_box(bbox, grid)
        records.append((unit, names, objects, bbox, (x, y, w, h)))

    # Selection A L'ECRAN, avec la boite meme qui servira au collage : selection
    # et placement ne peuvent donc pas se contredire.
    if args.only:
        px = grid.tile_px
        row, col = (int(v) for v in args.only.split("_")[1:3])
        keep = boxes_touching({r[0].name: r[4] for r in records},
                              (col * px, row * px, px, px))
        records = [r for r in records if r[0].name in keep]
    print(f"[unites] {len(records)} unites a rendre")

    # d'arriere en avant : le compositeur repassera dans cet ordre
    records.sort(key=lambda r: depth_key(r[2], grid), reverse=True)

    for order, (unit, names, objects, bbox, box) in enumerate(records):
        x, y, w, h = box
        line_path = args.out / f"{unit.name}_line.png"
        mask_path = args.out / f"{unit.name}_mask.png"
        index["units"].append({
            "name": unit.name, "way_ids": unit.way_ids, "order": order,
            "x": x, "y": y, "w": w, "h": h,
            "line": line_path.name, "mask": mask_path.name,
            "size_m": [round(bbox[2] - bbox[0], 2), round(bbox[3] - bbox[1], 2)],
        })
        if line_path.exists() and mask_path.exists() and not args.force:
            print(f"[unites] {unit.name} deja rendue, ignoree")
            continue

        only_visible(scene, names)
        aim_camera(cam, grid, bbox, args.camera_distance)

        iso_tiles.setup_line_pass(scene, args.line_thickness, args.samples)
        print(f"[unites] {order + 1}/{len(records)} {unit.name} "
              f"{w}x{h} px a ({x}, {y})")
        render_to(scene, line_path, w, h)

        setup_mask_pass(scene)
        render_to(scene, mask_path, w, h)

    (args.out / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[unites] -> {args.out / 'index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
