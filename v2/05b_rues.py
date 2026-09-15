"""Etape 5b — elargir les rues en retrecissant les ILOTS.

    blender -b -P v2/05b_rues.py

Lit castres_sol.blend, ecrit castres_rues.blend. S'insere entre le sol et les
toits, parce que les facades de l'etape 7 se calculent sur les murs : il faut
que les murs aient bouge avant.

POURQUOI. Mesure sur la zone, grille de 50 cm : 13,9 % de l'espace libre fait
moins de 3 m de large, 20,5 % moins de 4 m. Une ruelle de 3 m vue a 60 degres
est un trait ; un personnage de 4 mm n'y tient pas, et on ne peut pas y faire
marcher quelqu'un. C'est le vrai obstacle a la jouabilite, avant les toits.

C'EST UNE INVENTION, la deuxieme apres la variation de hauteur, et elle est
bornee de la meme facon : un retrait fixe, le meme partout, ecrit dans
config.json et annulable en remettant 0.

ON RETRECIT L'ILOT, PAS LA MAISON. Retrecir chaque batiment separement
decollerait les murs mitoyens : une rangee de dix maisons deviendrait dix
maisons isolees avec neuf fentes entre elles. Les batiments qui partagent un
noeud OSM forment un ilot, et c'est l'ilot entier qui se contracte autour de son
centre. Les murs interieurs bougent a peine, le pourtour recule, la rue gagne le
double du retrait.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

V2 = Path(__file__).resolve().parent
ROOT = V2.parent
CONFIG = V2 / "config.json"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def ilots(objets) -> list[list]:
    """Groupes de batiments qui se touchent, par sommets partages au sol."""
    cles: dict[tuple, list] = {}
    for obj in objets:
        mat = obj.matrix_world
        for v in obj.data.vertices:
            p = mat @ v.co
            if p.z > 0.6:
                continue                    # seul le pied du mur compte
            cle = (round(p.x, 1), round(p.y, 1))
            cles.setdefault(cle, []).append(obj.name)

    parent = {obj.name: obj.name for obj in objets}

    def trouver(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for voisins in cles.values():
        for autre in voisins[1:]:
            ra, rb = trouver(voisins[0]), trouver(autre)
            if ra != rb:
                parent[ra] = rb

    groupes: dict[str, list] = {}
    par_nom = {obj.name: obj for obj in objets}
    for nom in parent:
        groupes.setdefault(trouver(nom), []).append(par_nom[nom])
    return list(groupes.values())


def retrecir(groupe, retrait: float) -> float:
    """Contracte un ilot autour de son centre. Renvoie le retrait obtenu."""
    pts = [obj.matrix_world @ v.co for obj in groupe for v in obj.data.vertices]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    largeur, profondeur = max(xs) - min(xs), max(ys) - min(ys)
    cote = min(largeur, profondeur)
    if cote <= 2 * retrait + 1.0:
        return 0.0                          # trop petit : on n'y touche pas

    facteur = 1.0 - 2.0 * retrait / max(largeur, profondeur)
    centre = Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, 0.0))
    for obj in groupe:
        mat = obj.matrix_world
        inv = mat.inverted()
        for v in obj.data.vertices:
            p = mat @ v.co
            q = Vector((centre.x + (p.x - centre.x) * facteur,
                        centre.y + (p.y - centre.y) * facteur, p.z))
            v.co = inv @ q
        obj.data.update()
    return (1.0 - facteur) * max(largeur, profondeur) / 2.0


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_sol.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_rues.blend")
    p.add_argument("--retrait", type=float, default=None,
                   help="metres retires de chaque cote d'un ilot")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    retrait = (args.retrait if args.retrait is not None
               else cfg["zone"].get("retrait_ilot_m", 0.0))

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    coll = bpy.data.collections.get("buildings")
    if coll is None:
        sys.exit("Pas de collection buildings : reprendre a l'etape 2.")
    objets = [o for o in coll.objects if o.type == "MESH" and o.data.vertices]

    groupes = ilots(objets)
    tailles = sorted((len(g) for g in groupes), reverse=True)
    print(f"[rues] {len(objets)} batiments -> {len(groupes)} ilots "
          f"(le plus grand : {tailles[0]}, mediane {tailles[len(tailles) // 2]})")

    if retrait <= 0:
        print("[rues] retrait nul : rien n'est modifie")
    else:
        touches = sum(1 for g in groupes if retrecir(g, retrait) > 0.01)
        print(f"[rues] {touches}/{len(groupes)} ilots retrecis de {retrait:.2f} m "
              f"par cote, soit {2 * retrait:.1f} m gagnes par rue")

    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[rues] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
