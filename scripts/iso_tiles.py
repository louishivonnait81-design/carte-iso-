"""Rendu des tuiles isometriques depuis Blender.

Usage :
    blender -b assets/castres.blend -P scripts/iso_tiles.py -- \
        --rows 4 --cols 6 --tile 180 --center-latlon 43.6052 2.2405 --out tiles/

Produit, pour chaque tuile :
    tiles/tile_<L>_<C>.png       lignes noires sur blanc (Freestyle, EEVEE)
    tiles/tile_<L>_<C>_sem.png   aplats semantiques (Workbench, eclairage plat)
    tiles/index.json             grille, tailles, centre, ordre de rendu

Legende semantique (par defaut) :
    gris clair  = batiment      gris fonce = rue / trottoir
    vert        = vegetation    bleu       = eau
    blanc       = sol ouvert (place, cour, terrain nu)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import SEMANTIC_LINEAR, TileGrid  # noqa: E402

# --------------------------------------------------------------------------
# Categories semantiques
# --------------------------------------------------------------------------

# Couleurs posees sur les objets, definies une seule fois dans geo.py avec leur
# equivalent sRGB : c'est ce dernier que relisent stylize.py et qa.py.
SEMANTIC_COLORS = SEMANTIC_LINEAR

# Rapport d'epaisseur entre le trait de detail (faitages, aretiers) et celui des
# silhouettes de batiment.
DETAIL_RATIO = 0.45

# Regles de classement par defaut, appliquees dans cet ordre. Chaque mot-cle est
# cherche dans le nom de l'objet, le nom de ses collections et ses proprietes
# personnalisees (Blosm y recopie les tags OSM).
DEFAULT_RULES = {
    "water":      ["water", "riverbank", "waterway", "river", "stream", "canal", "agout"],
    "building":   ["building", "roof", "wall", "facade", "part"],
    "street":     ["highway", "road", "street", "footway", "path", "sidewalk", "pedestrian",
                   "bridge", "railway", "parking", "service", "residential", "tertiary",
                   "secondary", "primary", "unclassified", "cycleway", "steps"],
    "vegetation": ["vegetation", "tree", "forest", "wood", "grass", "park", "garden",
                   "scrub", "green", "meadow", "hedge", "leisure", "natural"],
    "ground":     ["ground", "terrain", "square", "pitch", "bare_rock", "landuse", "area"],
}


def _tokens(obj: bpy.types.Object) -> str:
    """Toutes les chaines qui peuvent renseigner sur la nature d'un objet."""
    parts = [obj.name]
    parts += [c.name for c in obj.users_collection]
    if obj.data is not None:
        parts.append(obj.data.name)
    for key in obj.keys():
        if key.startswith("_"):
            continue
        parts.append(str(key))
        value = obj[key]
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


# Marque explicite posee par osm_to_blend.py sur les objets dont la nature ne se
# devine pas au nom : une voie pietonne porte le tag `highway`, qui declencherait
# la regle "rue" avant toute autre. La marque prime donc sur les mots-cles.
SURFACE_PROPERTY = "surface"
SURFACE_TO_CATEGORY = {"open_ground": "ground", "street": "street"}


def classify(obj: bpy.types.Object, rules: dict[str, list[str]], default: str) -> str:
    marked = SURFACE_TO_CATEGORY.get(obj.get(SURFACE_PROPERTY))
    if marked:
        return marked
    text = _tokens(obj)
    for category, keywords in rules.items():
        if any(k in text for k in keywords):
            return category
    return default


# --------------------------------------------------------------------------
# Preparation de la scene
# --------------------------------------------------------------------------

def scene_origin(scene: bpy.types.Scene, override: tuple[float, float] | None) -> tuple[float, float]:
    """Origine geographique de la scene : Blosm l'ecrit dans scene["lat"/"lon"]."""
    if override is not None:
        return override
    try:
        return float(scene["lat"]), float(scene["lon"])
    except KeyError as exc:
        raise SystemExit(
            "La scene ne porte pas scene['lat'] / scene['lon'] (origine Blosm). "
            "Passer --origin-latlon LAT LON explicitement."
        ) from exc


def white_emission_material() -> bpy.types.Material:
    """Materiau d'override : blanc pur, insensible a l'eclairage."""
    mat = bpy.data.materials.get("ISO_WHITE_FLAT") or bpy.data.materials.new("ISO_WHITE_FLAT")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emission = nt.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    nt.links.new(emission.outputs["Emission"], out.inputs["Surface"])
    return mat


def white_world(scene: bpy.types.Scene) -> None:
    world = scene.world or bpy.data.worlds.new("ISO_WHITE_WORLD")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        bg.inputs["Strength"].default_value = 1.0


def flat_ribbon_profile(width: float) -> bpy.types.Object:
    """Courbe-profil a deux points : donne aux courbes de rue un ruban plat."""
    name = f"ISO_ROAD_PROFILE_{width:g}"
    existing = bpy.data.objects.get(name)
    if existing is not None:
        return existing
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "2D"
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (-width / 2.0, 0.0, 0.0, 1.0)
    spline.points[1].co = (width / 2.0, 0.0, 0.0, 1.0)
    obj = bpy.data.objects.new(name, curve)
    obj.hide_render = True
    bpy.context.scene.collection.objects.link(obj)
    return obj


def widen_street_curves(streets: list[bpy.types.Object], width: float) -> int:
    """Les rues importees sont des courbes sans epaisseur : on les transforme en
    rubans plats pour qu'elles couvrent une surface au rendu. La largeur vient de
    obj["road_width"] quand l'importateur l'a renseignee, sinon de --road-width."""
    profiles: dict[float, bpy.types.Object] = {}
    widened = 0
    for obj in streets:
        curve = obj.data
        if obj.type != "CURVE" or curve.bevel_object is not None or curve.bevel_depth:
            continue
        w = float(obj.get("road_width", width))
        if w not in profiles:
            profiles[w] = flat_ribbon_profile(w)
        curve.dimensions = "3D"
        curve.bevel_mode = "OBJECT"
        curve.bevel_object = profiles[w]
        curve.use_fill_caps = False
        widened += 1
    return widened


def add_ground_plane(grid: TileGrid, z: float) -> bpy.types.Object:
    """Sol blanc couvrant toute la grille : evite un fond vide sous la ville."""
    name = "ISO_GROUND"
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    # Large marge : la grille est un carre dans le plan image, sa projection au
    # sol est un parallelogramme plus etendu.
    size = 3.0 * max(grid.cols, grid.rows) * grid.tile_m
    bpy.ops.mesh.primitive_plane_add(size=size, location=(grid.center_xy[0], grid.center_xy[1], z))
    obj = bpy.context.active_object
    obj.name = name
    obj.color = SEMANTIC_COLORS["ground"]
    return obj


def setup_camera(scene: bpy.types.Scene, grid: TileGrid, distance: float) -> bpy.types.Object:
    name = "ISO_CAM"
    cam_data = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam_obj = bpy.data.objects.get(name)
    if cam_obj is None:
        cam_obj = bpy.data.objects.new(name, cam_data)
        scene.collection.objects.link(cam_obj)
    cam_obj.data = cam_data

    cam_data.type = "ORTHO"
    cam_data.ortho_scale = grid.tile_m          # une tuile = tile_m metres a l'ecran
    cam_data.clip_start = 1.0
    cam_data.clip_end = distance * 4.0
    cam_data.shift_x = 0.0
    cam_data.shift_y = 0.0

    target, view = grid.target, grid.basis.view
    cam_obj.location = tuple(target[i] - view[i] * distance for i in range(3))
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = grid.basis.euler
    scene.camera = cam_obj
    return cam_obj


def setup_output(scene: bpy.types.Scene, px: int) -> None:
    r = scene.render
    r.resolution_x = px
    r.resolution_y = px
    r.resolution_percentage = 100
    r.pixel_aspect_x = r.pixel_aspect_y = 1.0
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    r.image_settings.compression = 15
    # Pas de transformation de vue : le blanc doit rester blanc pur.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.sequencer_colorspace_settings.name = "sRGB"


def eevee_engine() -> str:
    """'BLENDER_EEVEE' en 3.x, 'BLENDER_EEVEE_NEXT' a partir de 4.2."""
    items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in items else "BLENDER_EEVEE"


def is_tree(obj: bpy.types.Object) -> bool:
    return obj.get("natural") == "tree" or obj.name.startswith("tree.")


def show_trees(scene: bpy.types.Scene, visible: bool) -> int:
    n = 0
    for obj in scene.objects:
        if is_tree(obj):
            obj.hide_render = not visible
            n += 1
    return n


def setup_line_pass(scene: bpy.types.Scene, thickness: float, samples: int,
                    engine: str = "cycles") -> None:
    # Cycles sur CPU par defaut : Freestyle y est supporte et, la scene etant un
    # aplat blanc emissif, quelques echantillons suffisent. EEVEE a besoin d'un
    # GPU ; en rendu logiciel il est dix fois plus lent.
    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = False
        scene.cycles.max_bounces = 0
    else:
        scene.render.engine = eevee_engine()
        eevee = getattr(scene, "eevee", None)
        if eevee is not None and hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = samples

    white_world(scene)
    view_layer = scene.view_layers[0]
    view_layer.material_override = white_emission_material()

    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"
    scene.render.line_thickness = thickness
    view_layer.use_freestyle = True

    fs = view_layer.freestyle_settings
    fs.mode = "EDITOR"
    # Un toit de tuiles canal a ~28 deg de pente : ses aretes (faite, aretiers)
    # forment des angles diedres de 124 a 141 deg. Le seuil par defaut (134 deg)
    # les ignore ; 160 deg les trace sans attraper les faces coplanaires.
    fs.crease_angle = math.radians(160.0)
    while fs.linesets:
        fs.linesets.remove(fs.linesets[0])

    # Deux jeux de lignes plutot qu'un seul, pour donner une hierarchie au
    # squelette : un trait uniforme met une arete de faitage au meme rang qu'une
    # silhouette de batiment, et le styliseur n'a aucun moyen de distinguer une
    # masse d'un detail. Les silhouettes sortent donc plus epaisses.
    def make_lineset(name: str, width: float, **flags):
        lineset = fs.linesets.new(name)
        for key in ("select_silhouette", "select_border", "select_crease",
                    "select_edge_mark", "select_contour", "select_external_contour",
                    "select_material_boundary", "select_ridge_valley",
                    "select_suggestive_contour"):
            setattr(lineset, key, flags.get(key, False))
        style = lineset.linestyle
        style.color = (0.0, 0.0, 0.0)
        style.thickness = width
        style.thickness_position = "CENTER"
        style.caps = "ROUND"
        style.use_chaining = True
        return lineset

    make_lineset("ISO_DETAIL", thickness * DETAIL_RATIO,
                 select_crease=True, select_edge_mark=True)
    make_lineset("ISO_MASSES", thickness,
                 select_silhouette=True, select_border=True,
                 select_contour=True, select_external_contour=True)


def setup_semantic_pass(scene: bpy.types.Scene) -> None:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.use_freestyle = False
    scene.view_layers[0].use_freestyle = False
    scene.view_layers[0].material_override = None

    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "OBJECT"
    shading.background_type = "VIEWPORT"
    shading.background_color = (1.0, 1.0, 1.0)
    shading.show_object_outline = False
    shading.show_specular_highlight = False
    shading.show_shadows = False
    shading.show_cavity = False
    scene.display.render_aa = "OFF"     # aplats nets, sans lissage


# --------------------------------------------------------------------------
# Boucle de rendu
# --------------------------------------------------------------------------

def render_tile(scene: bpy.types.Scene, cam: bpy.types.Object, tile, path: Path) -> None:
    cam.data.shift_x = tile.shift_x
    cam.data.shift_y = tile.shift_y
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="iso_tiles.py",
        description="Rend une grille de tuiles isometriques jointives depuis une scene Blosm.",
    )
    p.add_argument("--rows", type=int, default=4, help="nombre de lignes de la grille")
    p.add_argument("--cols", type=int, default=7, help="nombre de colonnes de la grille")
    p.add_argument("--tile", type=float, default=60.0,
                   help="largeur d'une tuile a l'ecran, en metres")
    p.add_argument("--px", type=int, default=2048, help="cote d'une tuile en pixels")
    p.add_argument("--center-latlon", type=float, nargs=2, metavar=("LAT", "LON"),
                   default=(43.60482, 2.24177), help="centre de la grille")
    p.add_argument("--origin-latlon", type=float, nargs=2, metavar=("LAT", "LON"), default=None,
                   help="origine de la scene si scene['lat'/'lon'] est absent")
    p.add_argument("--out", type=Path, default=Path("tiles"), help="dossier de sortie")
    p.add_argument("--elevation", type=float, default=45.0, help="elevation camera, degres")
    p.add_argument("--azimuth", type=float, default=45.0, help="azimut camera, degres")
    p.add_argument("--line-thickness", type=float, default=2.6,
                   help="epaisseur des silhouettes, px ; le detail vaut 45 % de cela")
    p.add_argument("--samples", type=int, default=8, help="echantillons de la passe lignes")
    p.add_argument("--line-engine", choices=["cycles", "eevee"], default="cycles",
                   help="moteur de la passe lignes")
    p.add_argument("--road-width", type=float, default=7.0,
                   help="largeur donnee aux courbes de rue, en metres")
    p.add_argument("--ground-z", type=float, default=-0.05,
                   help="altitude du plan de sol blanc")
    p.add_argument("--camera-distance", type=float, default=2000.0,
                   help="recul de la camera orthographique")
    p.add_argument("--no-ground", action="store_true", help="ne pas ajouter de plan de sol")
    p.add_argument("--trees", choices=["both", "sem", "none"], default="sem",
                   help="ou faire apparaitre les arbres. 'sem' (defaut) : dans la "
                        "passe semantique seulement — leur position est transmise "
                        "par le vert, sans imposer au styliseur un cercle nu a "
                        "recopier ; 'both' : aussi dans la passe lignes")
    p.add_argument("--only", default=None,
                   help="ne rendre que ces tuiles, ex. '0_0,0_1'")
    p.add_argument("--pass", dest="passes", choices=["line", "sem", "both"], default="both",
                   help="passe(s) a rendre")
    p.add_argument("--force", action="store_true", help="re-rendre les tuiles existantes")
    p.add_argument("--dump-categories", action="store_true",
                   help="afficher le classement des objets puis quitter")
    return p.parse_args(argv)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parse_args(argv)

    scene = bpy.context.scene
    origin = scene_origin(scene, tuple(args.origin_latlon) if args.origin_latlon else None)
    grid = TileGrid.build(
        rows=args.rows, cols=args.cols, tile_m=args.tile, tile_px=args.px,
        center_lat=args.center_latlon[0], center_lon=args.center_latlon[1],
        origin_lat=origin[0], origin_lon=origin[1],
        elevation_deg=args.elevation, azimuth_deg=args.azimuth,
    )

    print(f"[iso] origine scene  : lat {origin[0]} lon {origin[1]}")
    print(f"[iso] centre grille  : lat {grid.center_lat} lon {grid.center_lon} "
          f"-> x {grid.center_xy[0]:.2f} y {grid.center_xy[1]:.2f}")
    print(f"[iso] grille         : {grid.rows}x{grid.cols} tuiles de {grid.tile_m} m "
          f"({grid.mosaic_px[0]}x{grid.mosaic_px[1]} px)")

    # Classement des objets et couleur semantique associee.
    buckets: dict[str, list[bpy.types.Object]] = {k: [] for k in SEMANTIC_COLORS}
    for obj in scene.objects:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            continue
        category = classify(obj, DEFAULT_RULES, default="ground")
        buckets[category].append(obj)
        obj.color = SEMANTIC_COLORS[category]

    for category, objs in buckets.items():
        print(f"[iso] {category:<11}: {len(objs)} objets")
    if args.dump_categories:
        for category, objs in buckets.items():
            for obj in objs:
                print(f"  {category:<11} {obj.name}")
        return

    if buckets["building"] == [] and buckets["street"] == []:
        print("[iso] ATTENTION : aucun batiment ni rue reconnu. Verifier le nommage "
              "de la scene avec --dump-categories.")

    # les voies pietonnes sont des sols, mais elles ont besoin de la meme
    # largeur qu'une rue pour couvrir une surface au rendu
    widened = widen_street_curves(buckets["street"] + buckets["ground"], args.road_width)
    if widened:
        print(f"[iso] {widened} courbes de rue elargies a {args.road_width} m")
    if not args.no_ground:
        add_ground_plane(grid, args.ground_z)

    cam = setup_camera(scene, grid, args.camera_distance)
    setup_output(scene, grid.tile_px)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(grid.to_index(), indent=2), encoding="utf-8")
    print(f"[iso] index ecrit    : {out / 'index.json'}")

    wanted = set(args.only.split(",")) if args.only else None
    tiles = [t for t in grid.tiles()
             if wanted is None or t.name in wanted or f"{t.row}_{t.col}" in wanted]

    passes = []
    if args.passes in ("line", "both"):
        passes.append(("line", "", setup_line_pass))
    if args.passes in ("sem", "both"):
        passes.append(("sem", "_sem", lambda s: setup_semantic_pass(s)))

    for label, suffix, setup in passes:
        if label == "line":
            setup(scene, args.line_thickness, args.samples, args.line_engine)
            n = show_trees(scene, args.trees == "both")
        else:
            setup(scene)
            n = show_trees(scene, args.trees != "none")
        if n:
            print(f"[iso] {n} arbres " + ("visibles" if
                  (args.trees == "both" if label == "line" else args.trees != "none")
                  else "masques") + f" dans la passe {label}")
        for i, tile in enumerate(tiles, 1):
            path = out / f"{tile.name}{suffix}.png"
            if path.exists() and not args.force:
                print(f"[iso] {label} {tile.name} deja rendu, ignore")
                continue
            print(f"[iso] {label} {i}/{len(tiles)} -> {path}")
            render_tile(scene, cam, tile, path)

    print("[iso] termine")


if __name__ == "__main__":
    main()
