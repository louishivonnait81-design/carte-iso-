"""Etape 4 — quatre apercus, un par orientation, pour choisir.

    blender -b -P v2/04_previews.py
    python3 v2/04_previews.py -- --moteur CYCLES

Le fichier n'est ouvert qu'une fois et les materiaux aplatis une fois : seule la
camera tourne entre deux rendus. Les orientations viennent de config.json.

Apres cette etape, on s'arrete. L'orientation choisie est ecrite dans
config.json par la main de l'auteur, ou par `--figer 135`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

V2 = Path(__file__).resolve().parent
CONFIG = V2 / "config.json"

_spec = importlib.util.spec_from_file_location("camera_v2", V2 / "03_camera.py")
camera = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(camera)

import bpy  # noqa: E402


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_base.blend")
    p.add_argument("--out", type=Path, default=V2 / "previews")
    p.add_argument("--largeur", type=int, default=None)
    p.add_argument("--moteur", default=None)
    p.add_argument("--figer", type=float, default=None,
                   help="ecrire cette orientation dans config.json et ne rien rendre")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    if args.figer is not None:
        cfg["camera"]["rotation_z_deg"] = args.figer
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print(f"[apercus] orientation figee a Z={args.figer} dans {CONFIG}")
        return 0

    if cfg["zone"]["bbox"] is None:
        sys.exit("bbox absente de config.json : lancer v2/01_bbox.py d'abord.")

    largeur = args.largeur or cfg["rendu"]["largeur_apercu_px"]
    args.out.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene, n = camera.preparer(cfg, args.moteur)
    print(f"[apercus] {n} objets en blanc plat, moteur {scene.render.engine}, "
          f"X={cfg['camera']['rotation_x_deg']}")

    for z in cfg["orientations_a_tester"]:
        sortie = args.out / f"preview_Z{int(z):03d}.png"
        debut = time.time()
        w, h = camera.rendre(scene, cfg, float(z), largeur, sortie)
        print(f"[apercus] Z={int(z):3d}  {w:.0f} m x {h:.0f} m  "
              f"{scene.render.resolution_x}x{scene.render.resolution_y} px  "
              f"{time.time() - debut:5.1f} s  -> {sortie.name}")

    print(f"[apercus] {len(cfg['orientations_a_tester'])} apercus dans {args.out}")
    print("[apercus] choisir une orientation, puis : "
          "python3 v2/04_previews.py -- --figer <angle>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
