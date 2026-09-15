"""Diagnostic : les chemins sont-ils visibles ? (lit un .blend, n'ecrit rien)

    blender -b -P v2/mesure_rues.py -- --blend v2/castres_rues.blend --carte out.png

Extrait l'emprise au sol reelle des batiments — les faces du bas, jamais les
boites englobantes — puis passe la main a v2/jouabilite.py, qui mesure la
largeur DEGAGEE de chaque traversee de ruelle, ombre des murs deduite.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy

V2 = Path(__file__).resolve().parent
ROOT = V2.parent
CONFIG = V2 / "config.json"
for chemin in (str(ROOT / "scripts"), str(V2)):
    if chemin not in sys.path:
        sys.path.insert(0, chemin)

import numpy as np                                    # noqa: E402
from geo import latlon_to_xy                          # noqa: E402
import jouabilite as J                                # noqa: E402

Z_PIED = 0.6


def emprise(cfg, scene):
    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    x0, y0 = latlon_to_xy(lat0, lon0, scene["lat"], scene["lon"])
    x1, y1 = latlon_to_xy(lat1, lon1, scene["lat"], scene["lon"])
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def empreintes(objets):
    """(triangles 2D, hauteur du batiment) pour toutes les faces du bas."""
    tris, hs = [], []
    for obj in objets:
        mat = obj.matrix_world
        co = [mat @ v.co for v in obj.data.vertices]
        if not co:
            continue
        haut = max(p.z for p in co)
        for f in obj.data.polygons:
            idx = list(f.vertices)
            if any(co[k].z > Z_PIED for k in idx):
                continue
            for a, b in zip(idx[1:-1], idx[2:]):
                tris.append(((co[idx[0]].x, co[idx[0]].y),
                             (co[a].x, co[a].y), (co[b].x, co[b].y)))
                hs.append(max(haut, 0.1))
    return tris, hs


def carte(hauteur, cache, chemin: Path):
    """Image de controle : bati noir, sol cache gris, sol visible blanc."""
    from PIL import Image
    img = np.full(hauteur.shape, 255, dtype=np.uint8)
    img[cache] = 170
    img[hauteur > 0.01] = 0
    Image.fromarray(np.flipud(img)).save(chemin)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_rues.blend")
    p.add_argument("--carte", type=Path, default=None)
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("--pas", type=float, default=J.PAS_M)
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    coll = bpy.data.collections.get("buildings")
    if coll is None:
        sys.exit("Pas de collection buildings.")
    objets = [o for o in coll.objects if o.type == "MESH" and o.data.vertices]

    boite = emprise(cfg, scene)
    tris, hs = empreintes(objets)
    hauteur, _, _ = J.rasteriser(tris, hs, boite, args.pas)
    elev = 90.0 - cfg["camera"]["rotation_x_deg"]
    res = J.rapport(hauteur, args.pas, elev)
    res["blend"] = args.blend.name
    res["batiments"] = len(objets)
    res["hauteur_moyenne_m"] = float(np.mean(hs)) if hs else 0.0

    print(f"\n[mesure] {args.blend.name} — {len(objets)} batiments, "
          f"{100 * res['part_batie']:.1f} % du sol bati, "
          f"elevation {elev:.0f} deg")
    print(f"[mesure] sol libre reellement visible : "
          f"{100 * res['part_sol_visible']:.1f} %")
    for nom in ("nord_sud", "est_ouest"):
        r = res[nom]
        print(f"[mesure] chemins {nom:9s} : {r['traversees']:6d} traversees | "
              f"largeur med {r['largeur_mediane_m']:4.1f} m, p10 "
              f"{r['largeur_p10_m']:4.1f} m | DEGAGE med "
              f"{r['degage_median_m']:4.1f} m | jouables "
              f"{100 * r['part_jouable']:5.1f} % | invisibles "
              f"{100 * r['part_invisible']:5.1f} %")

    if args.carte:
        carte(hauteur, J.ombre(hauteur, args.pas, elev), args.carte)
        print(f"[mesure] carte de controle -> {args.carte}")
    if args.json:
        args.json.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
