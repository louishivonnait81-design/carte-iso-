"""Etape 12 — la vie de la rue : vehicules, terrasses, etals, velos.

    blender -b -P v2/12_vie.py

Lit castres_ouvert.blend, ecrit castres_vie.blend.

POURQUOI. Mesure comparative avec la planche MicroMacro, a echelle egale
(7000 px de rendu = 50 px par etage, comme la photo) : la reference encre 15,0 %
d'un quartier dense, ma carte 5,6 %. L'ecart n'est pas dans l'epaisseur du trait
— son profil est desormais identique — mais dans le CONTENU. La planche porte
des dizaines d'objets par pate de maisons ; la carte en comptait 57 pour toute
la zone.

D'OU VIENT CE QUI EST POSE. D'OpenStreetMap, comme le reste, et de nulle part
ailleurs :

  * les vehicules suivent l'axe des voies CARROSSABLES — residential et service,
    jamais pedestrian, footway ni steps. 24 et 15 voies respectivement dans la
    zone ;
  * les terrasses naissent des noeuds amenity=cafe / bar / restaurant /
    fast_food, et se posent sur le sol libre devant l'etablissement ;
  * les etals naissent des noeuds shop=* ;
  * les velos se rangent aux amenity=bicycle_parking, la ou l'etape 8 a deja
    pose les arceaux.

Rien n'est place au hasard sur le sol : un emplacement est refuse si ses quatre
coins ne tombent pas sur du sol libre, teste sur la grille de 25 cm des emprises
reelles. Un vehicule dans un mur se verrait de loin sur un dessin au trait.

LES PERSONNAGES NE SONT PAS ICI. Ils restent le calque separe prevu depuis le
debut, et ils attendent un accord explicite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

V2 = Path(__file__).resolve().parent
ROOT = V2.parent
CONFIG = V2 / "config.json"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(V2) not in sys.path:
    sys.path.insert(0, str(V2))

from geo import latlon_to_xy                                  # noqa: E402

CARROSSABLE = {"residential", "service", "unclassified", "tertiary",
               "secondary", "primary", "living_street"}
Z_CHAUSSEE = 0.12        # epaisseur de la chaussee posee a l'etape 5
Z_TROTTOIR = 0.14
PAS_VEHICULE = 9.0       # m entre deux vehicules le long d'une voie
DEPORT_VOIE = 1.9        # m entre l'axe de la voie et le flanc du vehicule
MARGE_BATI = 0.35        # m de degagement exige autour d'un objet pose


def alea(*cle) -> float:
    """Tirage reproductible dans [0,1) : deux executions posent la meme ville."""
    h = hashlib.blake2b(repr(cle).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2 ** 64


# --------------------------------------------------------------- les maillages
def cube(bm, centre, dims):
    r = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=r["verts"], vec=dims)
    bmesh.ops.translate(bm, verts=r["verts"], vec=centre)
    return r["verts"]


def cylindre(bm, centre, rayon, hauteur, axe="Z", segments=10):
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=segments,
                              radius1=rayon, radius2=rayon, depth=hauteur)
    if axe == "Y":
        bmesh.ops.rotate(bm, verts=r["verts"], cent=(0, 0, 0),
                         matrix=Vector((1, 0, 0)).to_track_quat("Z", "Y").to_matrix())
    bmesh.ops.translate(bm, verts=r["verts"], vec=centre)
    return r["verts"]


def maillage_voiture(long_=4.1, larg=1.78, haut=0.78, cabine=0.56):
    """Une caisse, une cabine en retrait, quatre roues. Vue a 41 degres, la
    silhouette et la ligne de pavillon suffisent : inutile de modeler plus."""
    bm = bmesh.new()
    cube(bm, (0, 0, 0.32 + haut / 2), (long_, larg, haut))
    cube(bm, (-0.25, 0, 0.32 + haut + cabine / 2 - 0.04),
         (long_ * 0.52, larg * 0.88, cabine))
    for sx in (1, -1):
        for sy in (1, -1):
            cylindre(bm, (sx * long_ * 0.32, sy * larg / 2, 0.32), 0.32, 0.18, "Y")
    return bm


def maillage_camionnette():
    bm = bmesh.new()
    cube(bm, (0, 0, 0.38 + 1.05), (5.3, 2.0, 2.1))
    cube(bm, (2.0, 0, 0.38 + 0.75), (1.4, 1.95, 1.5))
    for sx in (1, -1):
        for sy in (1, -1):
            cylindre(bm, (sx * 1.8, sy * 1.0, 0.38), 0.38, 0.22, "Y")
    return bm


def maillage_table():
    bm = bmesh.new()
    cylindre(bm, (0, 0, 0.71), 0.42, 0.06)
    cylindre(bm, (0, 0, 0.34), 0.06, 0.68)
    cylindre(bm, (0, 0, 0.03), 0.26, 0.05)
    return bm


def maillage_chaise():
    bm = bmesh.new()
    cube(bm, (0, 0, 0.44), (0.42, 0.42, 0.05))
    cube(bm, (-0.19, 0, 0.66), (0.05, 0.42, 0.45))
    for sx in (1, -1):
        for sy in (1, -1):
            cube(bm, (sx * 0.17, sy * 0.17, 0.21), (0.04, 0.04, 0.42))
    return bm


def maillage_parasol():
    bm = bmesh.new()
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=8,
                              radius1=1.25, radius2=0.05, depth=0.45)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 2.15))
    cylindre(bm, (0, 0, 1.0), 0.04, 2.0)
    return bm


def maillage_etal():
    """Un etal de devanture : le plateau incline et sa caisse."""
    bm = bmesh.new()
    cube(bm, (0, 0, 0.36), (1.5, 0.75, 0.72))
    v = cube(bm, (0, 0, 0.80), (1.5, 0.80, 0.16))
    for s in v:                      # on incline le plateau vers la rue
        if s.co.y > 0:
            s.co.z -= 0.13
    return bm


def maillage_cageot():
    bm = bmesh.new()
    cube(bm, (0, 0, 0.17), (0.52, 0.38, 0.34))
    cube(bm, (0, 0, 0.44), (0.46, 0.33, 0.22))
    return bm


def maillage_velo():
    bm = bmesh.new()
    for sx in (1, -1):
        cylindre(bm, (sx * 0.52, 0, 0.33), 0.33, 0.05, "Y", segments=12)
    cube(bm, (0, 0, 0.52), (0.95, 0.05, 0.06))
    cube(bm, (-0.30, 0, 0.72), (0.05, 0.05, 0.42))
    cube(bm, (-0.30, 0, 0.94), (0.05, 0.42, 0.05))
    cube(bm, (0.30, 0, 0.70), (0.05, 0.05, 0.36))
    return bm


FABRIQUES = {"voiture": maillage_voiture, "camionnette": maillage_camionnette,
             "table": maillage_table, "chaise": maillage_chaise,
             "parasol": maillage_parasol, "etal": maillage_etal,
             "cageot": maillage_cageot, "velo": maillage_velo}


# ------------------------------------------------------------- le sol libre
class SolLibre:
    """Grille des emprises baties : dit si un point porte quelque chose.

    On ne se fie pas aux boites englobantes : c'est la face du bas de chaque
    batiment qui est rasterisee. Une mesure de largeur de rue faite sur les
    boites avait deja annonce un gain nul sur un retrecissement bien reel.
    """

    PAS = 0.25

    def __init__(self, objets, boite):
        import numpy as np
        import jouabilite as J
        tris, hs = [], []
        for obj in objets:
            mat = obj.matrix_world
            co = [mat @ v.co for v in obj.data.vertices]
            if not co:
                continue
            for f in obj.data.polygons:
                idx = list(f.vertices)
                if any(co[k].z > 0.6 for k in idx):
                    continue
                for a, b in zip(idx[1:-1], idx[2:]):
                    tris.append(((co[idx[0]].x, co[idx[0]].y),
                                 (co[a].x, co[a].y), (co[b].x, co[b].y)))
                    hs.append(1.0)
        h, _, _ = J.rasteriser(tris, hs, boite, self.PAS)
        # une marge autour du bati : un objet ne doit pas fraler le mur
        n = max(1, int(round(MARGE_BATI / self.PAS)))
        occupe = h > 0.01
        for _ in range(n):
            occupe = (occupe | np.roll(occupe, 1, 0) | np.roll(occupe, -1, 0)
                      | np.roll(occupe, 1, 1) | np.roll(occupe, -1, 1))
        self.occupe = occupe
        self.x0, self.y0 = boite[0], boite[1]
        self.ny, self.nx = occupe.shape

    def libre(self, x: float, y: float) -> bool:
        i = int((x - self.x0) / self.PAS)
        j = int((y - self.y0) / self.PAS)
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            return False
        return not self.occupe[j, i]

    def place(self, x: float, y: float, dx: float, dy: float, angle: float) -> bool:
        """Les quatre coins d'un rectangle oriente tombent-ils sur du libre ?"""
        c, s = math.cos(angle), math.sin(angle)
        for sx in (-0.5, 0.5):
            for sy in (-0.5, 0.5):
                px = x + (sx * dx) * c - (sy * dy) * s
                py = y + (sx * dx) * s + (sy * dy) * c
                if not self.libre(px, py):
                    return False
        return True

    def devant(self, x: float, y: float, rayon: float = 8.0):
        """Point de sol libre le plus proche, pour poser une terrasse ou un etal.

        Renvoie (x, y, angle) ou l'angle regarde le batiment : une terrasse
        tourne le dos a sa facade.
        """
        for r in [v * 0.5 for v in range(2, int(rayon * 2) + 1)]:
            meilleur = None
            for k in range(24):
                a = 2 * math.pi * k / 24
                px, py = x + r * math.cos(a), y + r * math.sin(a)
                if self.place(px, py, 2.6, 2.6, 0.0):
                    d = (px - x) ** 2 + (py - y) ** 2
                    if meilleur is None or d < meilleur[0]:
                        meilleur = (d, px, py, a + math.pi)
            if meilleur:
                return meilleur[1], meilleur[2], meilleur[3]
        return None


# ------------------------------------------------------------------ les donnees
def lire_osm(cfg: dict, scene):
    """Voies carrossables, noeuds de commerce et parkings a velos de la zone."""
    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    olat, olon = scene["lat"], scene["lon"]
    racine = ET.parse(ROOT / cfg["import"]["source_osm"]).getroot()
    noeuds = {n.get("id"): (float(n.get("lat")), float(n.get("lon")))
              for n in racine.iter("node")}

    def dedans(lat, lon):
        return lat0 <= lat <= lat1 and lon0 <= lon <= lon1

    voies = []
    for w in racine.iter("way"):
        t = {x.get("k"): x.get("v") for x in w.findall("tag")}
        if t.get("highway") not in CARROSSABLE:
            continue
        pts = [noeuds[nd.get("ref")] for nd in w.findall("nd")
               if nd.get("ref") in noeuds]
        if len(pts) < 2 or not any(dedans(*p) for p in pts):
            continue
        voies.append((int(w.get("id")),
                      [latlon_to_xy(la, lo, olat, olon) for la, lo in pts]))

    terrasses, etals, velos = [], [], []
    for n in racine.iter("node"):
        lat, lon = noeuds[n.get("id")]
        if not dedans(lat, lon):
            continue
        t = {x.get("k"): x.get("v") for x in n.findall("tag")}
        xy = latlon_to_xy(lat, lon, olat, olon)
        nid = int(n.get("id"))
        if t.get("amenity") in ("cafe", "bar", "restaurant", "fast_food", "pub"):
            terrasses.append((nid, xy, t.get("amenity")))
        elif "shop" in t:
            etals.append((nid, xy, t["shop"]))
        elif t.get("amenity") == "bicycle_parking":
            velos.append((nid, xy, "velo"))
    return voies, terrasses, etals, velos


# ------------------------------------------------------------------ la pose
def poser_vehicules(voies, sol, poser) -> int:
    # Deux voies OSM se rejoignent souvent au meme carrefour, et chacune y
    # deposait son vehicule : le premier rendu montrait des voitures empilees.
    # On garde donc les positions deja prises.
    prises: list[tuple[float, float]] = []

    def libre_de_voisin(x, y, d=4.5):
        return all((x - px) ** 2 + (y - py) ** 2 > d * d for px, py in prises)

    n = 0
    for wid, pts in voies:
        reste = alea("depart", wid) * PAS_VEHICULE
        cote = 1 if alea("cote", wid) > 0.5 else -1
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            longueur = math.hypot(dx, dy)
            if longueur < 1e-6:
                continue
            ux, uy = dx / longueur, dy / longueur
            d = reste
            while d < longueur:
                px = x0 + ux * d - uy * cote * DEPORT_VOIE
                py = y0 + uy * d + ux * cote * DEPORT_VOIE
                angle = math.atan2(uy, ux)
                tirage = alea("genre", wid, round(d, 1))
                genre = "camionnette" if tirage > 0.82 else "voiture"
                gabarit = (5.6, 2.2) if genre == "camionnette" else (4.3, 1.9)
                if sol.place(px, py, *gabarit, angle) and libre_de_voisin(px, py):
                    poser(genre, px, py, Z_CHAUSSEE, angle)
                    prises.append((px, py))
                    n += 1
                cote = -cote
                d += PAS_VEHICULE
            reste = d - longueur
    return n


def poser_terrasses(terrasses, sol, poser) -> tuple[int, int]:
    tables = parasols = 0
    for nid, (x, y), genre in terrasses:
        ancre = sol.devant(x, y)
        if ancre is None:
            continue
        ax, ay, vers = ancre
        # deux rangees de deux tables, alignees le long de la facade
        tx, ty = -math.sin(vers), math.cos(vers)
        for i in range(4):
            u = (i % 2 - 0.5) * 2.1
            v = (i // 2) * 1.9
            px = ax + tx * u - math.cos(vers) * v
            py = ay + ty * u - math.sin(vers) * v
            if not sol.place(px, py, 2.0, 2.0, 0.0):
                continue
            poser("table", px, py, Z_TROTTOIR, 0.0)
            tables += 1
            for s in (1, -1):
                cx = px + tx * s * 0.75
                cy = py + ty * s * 0.75
                if sol.place(cx, cy, 0.6, 0.6, 0.0):
                    poser("chaise", cx, cy, Z_TROTTOIR, vers + (0 if s > 0 else math.pi))
            if alea("parasol", nid, i) > 0.5:
                poser("parasol", px, py, Z_TROTTOIR, 0.0)
                parasols += 1
    return tables, parasols


def poser_etals(etals, sol, poser) -> int:
    n = 0
    for nid, (x, y), genre in etals:
        ancre = sol.devant(x, y, rayon=6.0)
        if ancre is None:
            continue
        ax, ay, vers = ancre
        angle = vers + math.pi / 2
        if sol.place(ax, ay, 1.8, 1.1, angle):
            poser("etal", ax, ay, Z_TROTTOIR, angle)
            n += 1
        tx, ty = -math.sin(vers), math.cos(vers)
        for s in (1, -1):
            if alea("cageot", nid, s) < 0.45:
                continue
            cx, cy = ax + tx * s * 1.15, ay + ty * s * 1.15
            if sol.place(cx, cy, 0.7, 0.6, angle):
                poser("cageot", cx, cy, Z_TROTTOIR, angle + alea("t", nid, s) * 0.5)
    return n


def poser_velos(velos, sol, poser) -> int:
    n = 0
    for nid, (x, y), _ in velos:
        vers = alea("velo", nid) * math.pi
        tx, ty = math.cos(vers + math.pi / 2), math.sin(vers + math.pi / 2)
        for k in (-1, 0, 1):
            px, py = x + tx * k * 0.65, y + ty * k * 0.65
            if sol.place(px, py, 1.3, 0.6, vers):
                poser("velo", px, py, Z_TROTTOIR, vers)
                n += 1
    return n


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--blend", type=Path, default=V2 / "castres_ouvert.blend")
    p.add_argument("--out", type=Path, default=V2 / "castres_vie.blend")
    args = p.parse_args(argv)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene

    lat0, lon0, lat1, lon1 = cfg["zone"]["bbox"]
    a = latlon_to_xy(lat0, lon0, scene["lat"], scene["lon"])
    b = latlon_to_xy(lat1, lon1, scene["lat"], scene["lon"])
    boite = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

    batis = [o for o in bpy.data.collections["buildings"].objects
             if o.type == "MESH" and o.data.vertices]
    sol = SolLibre(batis, boite)
    print(f"[vie] sol libre : {100 * (1 - sol.occupe.mean()):.0f} % de la zone, "
          f"marge de {MARGE_BATI:.2f} m autour du bati")

    coll = bpy.data.collections.get("vie")
    if coll:
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        coll = bpy.data.collections.new("vie")
        scene.collection.children.link(coll)

    maillages = {}
    for genre, fabrique in FABRIQUES.items():
        bm = fabrique()
        mesh = bpy.data.meshes.new(f"V2_{genre.upper()}")
        bm.to_mesh(mesh)
        bm.free()
        maillages[genre] = mesh

    compte: dict[str, int] = {}

    def poser(genre, x, y, z, angle):
        obj = bpy.data.objects.new(f"{genre}.{len(coll.objects):04d}",
                                   maillages[genre])
        obj.location = (x, y, z)
        obj.rotation_euler = (0.0, 0.0, angle)
        coll.objects.link(obj)
        compte[genre] = compte.get(genre, 0) + 1

    voies, terrasses, etals, velos = lire_osm(cfg, scene)
    print(f"[vie] OSM : {len(voies)} voies carrossables, {len(terrasses)} cafes "
          f"et restaurants, {len(etals)} commerces, {len(velos)} parkings a velos")

    poser_vehicules(voies, sol, poser)
    poser_terrasses(terrasses, sol, poser)
    poser_etals(etals, sol, poser)
    poser_velos(velos, sol, poser)

    for genre, n in sorted(compte.items(), key=lambda kv: -kv[1]):
        print(f"[vie] {genre:<12} {n:4d}")
    print(f"[vie] {sum(compte.values())} objets, {len(maillages)} maillages partages")

    bpy.ops.wm.save_as_mainfile(filepath=str(args.out))
    print(f"[vie] -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
