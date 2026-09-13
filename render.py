#!/usr/bin/env python3
"""Lance le rendu Blender des tuiles, avec ou sans binaire Blender installe.

    python render.py --rows 4 --cols 6 --tile 180 --center-latlon 43.6052 2.2405 --out tiles/

Cherche Blender dans cet ordre :
  1. $BLENDER_BIN
  2. `blender` dans le PATH
  3. ./third_party/blender*/blender
  4. le module pip `bpy` (execution du script dans l'interpreteur courant)
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLEND = ROOT / "assets" / "castres.blend"
ISO_TILES = ROOT / "scripts" / "iso_tiles.py"


def find_blender() -> str | None:
    env = os.environ.get("BLENDER_BIN")
    if env and Path(env).exists():
        return env
    found = shutil.which("blender")
    if found:
        return found
    for candidate in sorted(glob.glob(str(ROOT / "third_party" / "blender*" / "blender"))):
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def have_bpy_module() -> bool:
    try:
        import bpy  # noqa: F401
    except Exception:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--blend", type=Path, default=BLEND, help="fichier .blend a ouvrir")
    parser.add_argument("--print-command", action="store_true",
                        help="afficher la commande sans l'executer")
    args, passthrough = parser.parse_known_args()

    if not args.blend.exists():
        sys.exit(f"Scene introuvable : {args.blend}\n"
                 "Deposer la scene Blosm dans assets/castres.blend avant de rendre.")

    blender = find_blender()
    if blender:
        cmd = [blender, "-b", str(args.blend), "-P", str(ISO_TILES), "--", *passthrough]
    elif have_bpy_module():
        cmd = [sys.executable, "-c",
               f"import bpy; bpy.ops.wm.open_mainfile(filepath={str(args.blend)!r}); "
               f"exec(open({str(ISO_TILES)!r}).read())",
               "--", *passthrough]
    else:
        sys.exit(
            "Blender introuvable.\n"
            "  - installer le module pip : pip install bpy\n"
            "  - ou poser le binaire dans third_party/blender-3.6.x-linux-x64/blender\n"
            "  - ou definir BLENDER_BIN=/chemin/vers/blender\n"
            "Note : download.blender.org est bloque par le proxy reseau de cet "
            "environnement ; le module pip bpy, lui, s'installe depuis PyPI."
        )

    print("$", " ".join(cmd))
    if args.print_command:
        return 0
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
