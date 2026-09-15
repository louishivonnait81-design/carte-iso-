"""Etape 5b — rendre les chemins VISIBLES. Trois deformations assumees.

    blender -b -P v2/05b_rues.py

Lit castres_sol.blend, ecrit castres_rues.blend. S'insere entre le sol et les
toits, parce que les facades de l'etape 7 se calculent sur les murs : il faut
que les murs aient bouge avant.

C'est la seule etape qui s'ecarte volontairement d'OpenStreetMap. Tout ce qui
s'y fait est borne, ecrit dans config.json, et annulable en remettant 0.

CE QUE L'OEIL MESURE. Une ruelle n'est pas visible parce qu'elle est large :
elle est visible parce qu'il y reste du sol DEGAGE. La camera regarde du
sud-ouest a 60 degres ; un mur de hauteur h avale 0,408 h de largeur apparente.
Avec les 10 m de hauteur moyenne de l'import, ce sont 4,1 m avales — une ruelle
de 4 m n'a plus un pixel de sol, a n'importe quelle resolution. Mesure sur la
zone, grille de 25 cm (v2/jouabilite.py) : avant cette etape, 13,7 % des
traversees de ruelle nord-sud et 14,5 % des est-ouest etaient entierement
noires, et 28 % seulement des traversees interieures aux ilots etaient jouables.

TROIS LEVIERS, mesures separement.

1. SOUDER les fentes internes. 85 % des traversees invisibles n'etaient pas des
   rues — 93 % sur le seul axe nord-sud : c'etaient des fentes A L'INTERIEUR d'un ilot — deux maisons mitoyennes
   saisies dans OSM avec 40 cm d'ecart, une courette, un jour de souffrance. Le
   retrait d'ilot ne peut rien pour elles : l'ilot se contracte d'un bloc. On
   recolle donc les murs voisins de moins de 2,5 m. Sous 2,5 m personne ne passe
   : la fente n'est pas un chemin, c'est du bruit, et un pate de maisons se lit
   mieux en masse pleine. 686 murs recolles.

2. RETRECIR les ilots, ce qui elargit les rues. Le retrait s'applique MAINTENANT
   AXE PAR AXE. Une mise a l'echelle uniforme reculait un ilot allonge de
   1,2 m dans sa longueur mais de 0,24 m seulement dans sa largeur : les ruelles
   qui longent un ilot ne gagnaient presque rien, et ce sont justement celles que
   l'oeil ne voyait plus.

3. BAISSER les batiments. C'est le levier qui ouvre l'interieur des ilots, la ou
   la geometrie du plan ne peut rien. Un facteur, jamais un plafond : un plafond
   met toutes les maisons a la meme hauteur et rend la ligne de toits plate,
   exactement ce que la variation de hauteur cherchait a eviter.

RESULTAT MESURE, a 60 degres, soudure 2,5 m + retrait 2,0 m + hauteurs x0,7 :
traversees jouables 73,1 -> 84,1 % (nord-sud) et 64,8 -> 88,3 % (est-ouest) ;
entierement noires 13,7 -> 6,8 % et 14,5 -> 2,9 % ; sol libre reellement visible
82,4 -> 88,9 %. Surtout : des 2521 traversees de RUE — celles qui separent deux
ilots — il n'en reste PAS UNE d'invisible, sur les deux axes. Ce qui reste noir
est a l'interieur des ilots : des cours, pas des chemins.

ON RETRECIT L'ILOT, PAS LA MAISON. Retrecir chaque batiment separement
decollerait les murs mitoyens : une rangee de dix maisons deviendrait dix
maisons isolees avec neuf fentes entre elles. Les batiments qui partagent un
noeud OSM forment un ilot, et c'est l'ilot entier qui se contracte.
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

Z_PIED = 0.6            # au-dela, ce n'est plus le pied du mur
COTE_MIN_ILOT = 3.0     # un ilot ne descend jamais sous 3 m de cote


def ilots(objets) -> list[list]:
    """Groupes de batiments qui se touchent, par sommets partages au sol."""
    cles: dict[tuple, list] = {}
    for obj in objets:
        mat = obj.matrix_world
        for v in obj.data.vertices:
            p = mat @ v.co
            if p.z > Z_PIED:
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


def colonnes(obj) -> dict:
    """{(x,y) : indices des sommets} — un mur vertical se deplace d'un bloc.

    Bouger le seul sommet du bas laisserait le haut du mur en arriere et
    tordrait la maison ; c'est la colonne entiere qui se deplace.
    """
    d: dict[tuple, list] = {}
    mat = obj.matrix_world
    for i, v in enumerate(obj.data.vertices):
        p = mat @ v.co
        d.setdefault((round(p.x, 2), round(p.y, 2)), []).append(i)
    return d


def souder(groupe, seuil: float) -> int:
    """Recolle les murs de deux batiments VOISINS du meme ilot.

    Deux colonnes de deux batiments distincts distantes de moins de `seuil` sont
    ramenees a leur milieu. Un paquet ne prend jamais deux colonnes du meme
    batiment : sans cela une petite maison se refermerait sur elle-meme.
    """
    if seuil <= 0:
        return 0
    cols = []
    for obj in groupe:
        for (x, y), idx in colonnes(obj).items():
            cols.append([obj, idx, Vector((x, y, 0.0))])

    case: dict[tuple, list] = {}
    for n, (_, _, p) in enumerate(cols):
        case.setdefault((int(p.x // seuil), int(p.y // seuil)), []).append(n)

    parent = list(range(len(cols)))
    membres = {n: {id(cols[n][0])} for n in range(len(cols))}

    def trouver(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for (cx, cy), dedans in case.items():
        voisins = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                voisins += case.get((cx + dx, cy + dy), [])
        for a in dedans:
            for b in voisins:
                if a >= b or cols[a][0] is cols[b][0]:
                    continue
                if (cols[a][2] - cols[b][2]).length > seuil:
                    continue
                ra, rb = trouver(a), trouver(b)
                if ra == rb or membres[ra] & membres[rb]:
                    continue                # deux murs d'une meme maison
                parent[ra] = rb
                membres[rb] |= membres[ra]

    paquets: dict[int, list] = {}
    for n in range(len(cols)):
        paquets.setdefault(trouver(n), []).append(n)

    bouges = 0
    for paquet in paquets.values():
        if len(paquet) < 2:
            continue
        centre = sum((cols[n][2] for n in paquet), Vector((0, 0, 0))) / len(paquet)
        for n in paquet:
            obj, idx, p = cols[n]
            if (p - centre).length < 1e-4:
                continue
            mat = obj.matrix_world
            inv = mat.inverted()
            for i in idx:
                q = mat @ obj.data.vertices[i].co
                obj.data.vertices[i].co = inv @ Vector((centre.x, centre.y, q.z))
            bouges += 1
    for obj in groupe:
        obj.data.update()
    return bouges


def retrecir(groupe, retrait: float, echelle_h: float = 1.0) -> tuple[float, float]:
    """Contracte un ilot autour de son centre, AXE PAR AXE, et baisse le bati.

    Renvoie les retraits obtenus en X et en Y. Un ilot deja plus etroit que
    COTE_MIN_ILOT ne recule pas de ce cote-la : il disparaitrait.
    """
    pts = [obj.matrix_world @ v.co for obj in groupe for v in obj.data.vertices]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    largeur, profondeur = max(xs) - min(xs), max(ys) - min(ys)

    rx = min(retrait, max(0.0, (largeur - COTE_MIN_ILOT) / 2))
    ry = min(retrait, max(0.0, (profondeur - COTE_MIN_ILOT) / 2))
    fx = 1.0 - 2 * rx / largeur if largeur > 1e-6 else 1.0
    fy = 1.0 - 2 * ry / profondeur if profondeur > 1e-6 else 1.0
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    if abs(fx - 1) < 1e-9 and abs(fy - 1) < 1e-9 and abs(echelle_h - 1) < 1e-9:
        return 0.0, 0.0
    for obj in groupe:
        mat = obj.matrix_world
        inv = mat.inverted()
        for v in obj.data.vertices:
            p = mat @ v.co
            v.co = inv @ Vector((cx + (p.x - cx) * fx,
                                 cy + (p.y - cy) * fy,
                                 p.z * echelle_h))
        obj.data.update()
    return rx, ry


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_sol.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_rues.blend")
    p.add_argument("--retrait", type=float, default=None,
                   help="metres retires de chaque cote d'un ilot")
    p.add_argument("--soudure", type=float, default=None,
                   help="fente interieure en dessous de laquelle on recolle")
    p.add_argument("--echelle-hauteur", type=float, default=None)
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    zone = cfg["zone"]
    retrait = args.retrait if args.retrait is not None else zone.get("retrait_ilot_m", 0.0)
    soudure = args.soudure if args.soudure is not None else zone.get("soudure_ilot_m", 0.0)
    ech_h = (args.echelle_hauteur if args.echelle_hauteur is not None
             else zone.get("echelle_hauteur", 1.0))

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    coll = bpy.data.collections.get("buildings")
    if coll is None:
        sys.exit("Pas de collection buildings : reprendre a l'etape 2.")
    objets = [o for o in coll.objects if o.type == "MESH" and o.data.vertices]

    groupes = ilots(objets)
    tailles = sorted((len(g) for g in groupes), reverse=True)
    print(f"[rues] {len(objets)} batiments -> {len(groupes)} ilots "
          f"(le plus grand : {tailles[0]}, mediane {tailles[len(tailles) // 2]})")

    if soudure > 0:
        recolles = sum(souder(g, soudure) for g in groupes)
        print(f"[rues] fentes interieures : {recolles} murs recolles "
              f"sous {soudure:.1f} m")

    if retrait <= 0 and abs(ech_h - 1) < 1e-9:
        print("[rues] retrait nul et hauteur inchangee : la geometrie reste OSM")
    else:
        faits = [retrecir(g, retrait, ech_h) for g in groupes]
        touches = sum(1 for rx, ry in faits if max(rx, ry) > 0.01)
        print(f"[rues] {touches}/{len(groupes)} ilots retrecis jusqu'a "
              f"{retrait:.2f} m par cote et par axe, soit {2 * retrait:.1f} m "
              f"gagnes par rue")
        if abs(ech_h - 1) > 1e-9:
            hauts = [max((o.matrix_world @ v.co).z for v in o.data.vertices)
                     for o in objets]
            print(f"[rues] hauteurs x{ech_h:.2f} : moyenne "
                  f"{sum(hauts) / len(hauts):.1f} m, max {max(hauts):.1f} m")

    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[rues] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
