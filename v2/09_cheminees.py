"""Etape 9 — les cheminees, sur le faitage des toits en croupe.

    blender -b -P v2/09_cheminees.py

Lit castres_mobilier.blend, ecrit castres_final.blend.

Une souche par tranche de longueur de faitage, posee SUR le faitage et non au
hasard sur le pan : c'est la ou elles sont en vrai, et c'est la seule ligne du
toit que l'on connaisse sans rien inventer.

Les toits a acrotere n'en recoivent pas. On ne sait pas ou passe leur faitage —
ils n'en ont pas — et une souche posee au milieu d'une terrasse serait un ajout
gratuit sur 70 % des batiments.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
import bmesh

V2 = Path(__file__).resolve().parent

SOUCHE = (0.55, 0.55, 1.20)     # largeur, profondeur, hauteur
PAR_METRE = 1 / 9.0             # une souche tous les neuf metres de faitage
MIN_FAITAGE = 3.0               # m


def aretes_de_faitage(bm, tolerance: float = 0.15):
    """Aretes horizontales du niveau le plus haut, entre deux PANS INCLINES.

    Le critere doit porter sur la pente, pas sur "pas tout a fait horizontal".
    Premiere version, avec un simple abs(normal.z) < 0,98 : 1101 souches sur 263
    batiments, alors que 79 seulement ont une croupe. Les murs verticaux d'un
    acrotere passaient le test. Un vrai pan de toit a une normale franchement
    oblique — ni verticale, ni horizontale.
    """
    def est_un_pan(face) -> bool:
        return 0.15 < abs(face.normal.z) < 0.92

    candidates = [e for e in bm.edges if len(e.link_faces) == 2
                  and all(est_un_pan(f) for f in e.link_faces)
                  and abs(e.verts[0].co.z - e.verts[1].co.z) < 0.05]
    if not candidates:
        return []
    zmax = max(e.verts[0].co.z for e in candidates)
    return [e for e in candidates if zmax - e.verts[0].co.z <= tolerance]


def poser(obj, bm_out) -> int:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    aretes = aretes_de_faitage(bm)
    longueur = sum(e.calc_length() for e in aretes)
    if longueur < MIN_FAITAGE:
        bm.free()
        return 0

    combien = max(1, round(longueur * PAR_METRE))
    aretes.sort(key=lambda e: -e.calc_length())
    mat = obj.matrix_world
    poses = 0
    for i in range(combien):
        arete = aretes[i % len(aretes)]
        a, b = (v.co for v in arete.verts)
        # reparties le long de l'arete, jamais toutes au meme point
        t = (i // len(aretes) + 1) / (i // len(aretes) + 2)
        milieu = mat @ (a.lerp(b, t))
        res = bmesh.ops.create_cube(bm_out, size=1.0)
        bmesh.ops.scale(bm_out, verts=res["verts"], vec=SOUCHE)
        bmesh.ops.translate(bm_out, verts=res["verts"],
                            vec=(milieu.x, milieu.y, milieu.z + SOUCHE[2] / 2 - 0.2))
        poses += 1
    bm.free()
    return poses



def _ranger(scene, objet, nom_collection: str):
    """Range l'objet dans une collection NOMMEE.

    Ce n'est pas du rangement : c'est ce qui permet a Freestyle de lui donner sa
    propre epaisseur de trait. Sans collection, tout le dessin sort au meme
    poids de ligne — le joint de dallage aussi fort que le mur — et la
    hierarchie qui fait lire un dessin au trait disparait.
    """
    coll = bpy.data.collections.get(nom_collection)
    if coll is None:
        coll = bpy.data.collections.new(nom_collection)
        scene.collection.children.link(coll)
    coll.objects.link(objet)
    return objet


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_mobilier.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_final.blend")
    args = p.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    coll = bpy.data.collections.get("buildings")

    bm = bmesh.new()
    total = batiments = 0
    for obj in list(coll.objects):
        if obj.type != "MESH" or not obj.data.polygons:
            continue
        n = poser(obj, bm)
        total += n
        batiments += 1 if n else 0

    mesh = bpy.data.meshes.new("V2_CHEMINEES")
    bm.to_mesh(mesh)
    bm.free()
    _ranger(scene, bpy.data.objects.new("V2_CHEMINEES", mesh), "cheminees")

    print(f"[cheminees] {total} souches sur {batiments} batiments a faitage")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[cheminees] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
