"""Etape 2 — import OSM vers castres_base.blend.

    blender -b -P v2/02_import.py            # via Blosm, si l'addon est present
    python3 v2/02_import.py                  # via le convertisseur du depot

Deux chemins, et le script DIT lequel il a pris.

Blosm est la voie prevue par le brief. Elle demande l'addon, donc un vrai
Blender, donc la machine de l'auteur. Le conteneur distant n'a ni l'un ni
l'autre : il porte bpy en module pip, sans addon.

Le depot contient deja scripts/osm_to_blend.py, ecrit plus tot dans ce projet
precisement parce que Blosm n'etait pas disponible. Il lit le meme fichier OSM
et produit les memes categories — batiments avec hauteurs, voies, eau,
vegetation. C'est le repli, et ce n'est pas un equivalent exact : les geometries
ne seront pas au sommet pres celles de Blosm. Pour valider un perimetre et un
angle, cela suffit ; pour la suite, il faudra trancher.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = Path(__file__).resolve().parent
CONFIG = V2 / "config.json"
SORTIE = V2 / "castres_base.blend"


def blosm_disponible() -> str | None:
    try:
        import addon_utils
    except ImportError:
        return None
    for module in addon_utils.modules():
        nom = module.__name__ or ""
        if "blosm" in nom.lower() or "blender-osm" in nom.lower():
            return nom if addon_utils.check(nom)[1] else None
    return None


def importer_par_blosm(cfg: dict, nom_addon: str) -> None:
    import bpy

    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.blosm.minLat, scene.blosm.maxLat = lat0, lat1
    scene.blosm.minLon, scene.blosm.maxLon = lon0, lon1
    scene.blosm.dataType = "osm"
    scene.blosm.mode = "3Dsimple"
    scene.blosm.defaultLevels = max(1, round(cfg["import"]["hauteur_defaut_m"] / 3.0))
    for calque, actif in (("buildings", True), ("highways", True),
                          ("water", True), ("forests", True), ("vegetation", True)):
        if hasattr(scene.blosm, calque):
            setattr(scene.blosm, calque, actif)
    bpy.ops.blosm.import_data()
    bpy.ops.wm.save_as_mainfile(filepath=str(SORTIE))
    print(f"[import] Blosm ({nom_addon}) -> {SORTIE}")


def importer_par_convertisseur(cfg: dict) -> int:
    osm = ROOT / cfg["import"]["source_osm"]
    if not osm.exists():
        sys.exit(f"{osm} introuvable : relancer v2/01_bbox.py.")
    cmd = [sys.executable, str(ROOT / "scripts" / "osm_to_blend.py"), str(osm),
           "--out", str(SORTIE),
           "--bbox", *[str(v) for v in cfg["zone"]["bbox"]],
           "--default-height", str(cfg["import"]["hauteur_defaut_m"]),
           # aucune variation de hauteur : le brief demande une valeur par
           # defaut nette de 9 m, pas une valeur bruitee
           "--jitter", "0"]
    print("[import] Blosm absent -> repli sur scripts/osm_to_blend.py")
    print("[import] " + " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if cfg["zone"]["bbox"] is None:
        sys.exit("bbox absente de config.json : lancer v2/01_bbox.py d'abord.")

    nom = blosm_disponible()
    if nom:
        importer_par_blosm(cfg, nom)
        return 0
    return importer_par_convertisseur(cfg)


if __name__ == "__main__":
    sys.exit(main())
