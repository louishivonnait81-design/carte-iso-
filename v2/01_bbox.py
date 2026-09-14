"""Etape 1 — perimetre du vieux Castres. N'importe rien, n'ecrit que config.json.

    python3 v2/01_bbox.py                     # depuis l'extrait OSM local
    python3 v2/01_bbox.py --source overpass   # en interrogeant Overpass

La bbox n'est pas saisie a la main : elle est calculee depuis les limites
NOMMEES de la zone, telles que la brief les donne. On prend tous les noeuds des
voies portant ces noms, on englobe, on ajoute la marge.

Deux sources possibles pour ces noeuds :

  * `extract` (defaut) : le fichier OSM deja telecharge. Aucun reseau. C'est la
    seule voie possible depuis le conteneur distant, dont la politique reseau
    refuse Nominatim et Overpass.
  * `overpass` : une requete par nom. A lancer depuis une machine qui a le
    reseau ; le resultat est identique, a ceci pres qu'il n'est pas tronque par
    les bords du fichier local.

Le script DIT s'il a ete tronque. L'extrait local s'arrete a 30 m au sud et 42 m
a l'ouest des reperes : sans cet avertissement, la marge de 60 m serait
silencieusement rognee de ce cote-la.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(__file__).resolve().parent / "config.json"

# Degres -> metres, a la latitude de Castres. La projection locale suffit
# largement sur une zone d'un kilometre.
M_PAR_DEG_LAT = 110540.0


def m_par_deg_lon(lat: float) -> float:
    return 111320.0 * math.cos(math.radians(lat))


def noeuds_des_voies_nommees(osm_path: Path, noms: list[str]):
    """Tous les noeuds des voies dont le nom figure dans `noms`, et les bounds."""
    voulus = {n.lower() for n in noms}
    nodes: dict[int, tuple[float, float]] = {}
    ways: dict[int, list[int]] = {}
    nommees: list[int] = []
    bounds = None

    for _, el in ET.iterparse(osm_path, events=("end",)):
        if el.tag == "bounds":
            bounds = (float(el.get("minlat")), float(el.get("minlon")),
                      float(el.get("maxlat")), float(el.get("maxlon")))
        elif el.tag == "node":
            nodes[int(el.get("id"))] = (float(el.get("lat")), float(el.get("lon")))
            el.clear()
        elif el.tag == "way":
            wid = int(el.get("id"))
            ways[wid] = [int(n.get("ref")) for n in el.findall("nd")]
            nom = next((t.get("v") for t in el.findall("tag")
                        if t.get("k") == "name"), None)
            if nom and nom.lower() in voulus:
                nommees.append(wid)
            el.clear()

    points, trouves = [], set()
    for wid in nommees:
        nom_pts = [nodes[n] for n in ways[wid] if n in nodes]
        if nom_pts:
            points.extend(nom_pts)
            trouves.add(wid)
    return points, bounds, len(trouves)


def centre_du_lieu(osm_path: Path, nom: str):
    """Centre du polygone portant ce nom. Sert d'ancre au coeur jouable."""
    voulu = nom.lower()
    nodes, pts = {}, []
    for _, el in ET.iterparse(osm_path, events=("end",)):
        if el.tag == "node":
            nodes[int(el.get("id"))] = (float(el.get("lat")), float(el.get("lon")))
            el.clear()
        elif el.tag == "way":
            etiquette = next((tag.get("v") for tag in el.findall("tag")
                              if tag.get("k") == "name"), None)
            if etiquette and etiquette.lower() == voulu:
                refs = [int(n.get("ref")) for n in el.findall("nd")]
                pts.extend(nodes[r] for r in refs if r in nodes)
            el.clear()
    if not pts:
        sys.exit(f"Lieu introuvable dans l'extrait : {nom}")
    return (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))


def englobe(points):
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return min(lats), min(lons), max(lats), max(lons)


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", choices=["extract", "overpass"], default="extract")
    p.add_argument("--osm", type=Path, default=ROOT / "assets" / "castres.osm")
    p.add_argument("--marge", type=float, default=None,
                   help="marge en metres ; par defaut celle de config.json")
    p.add_argument("--coeur", action="store_true",
                   help="coeur jouable a l'echelle MicroMacro, au lieu de toute la zone")
    p.add_argument("--centre", default="Place Jean Jaurès",
                   help="lieu servant d'ancre au coeur")
    p.add_argument("--cote", type=float, default=180.0,
                   help="cote du coeur en metres")
    p.add_argument("--dry-run", action="store_true", help="ne pas ecrire config.json")
    args = p.parse_args()

    if args.source == "overpass":
        print("[bbox] source overpass : a lancer depuis une machine qui a le reseau.")
        print("[bbox] ce conteneur ne peut pas l'atteindre (politique reseau).")
        return 2

    if not args.osm.exists():
        sys.exit(f"{args.osm} introuvable.")

    if args.coeur:
        # COEUR JOUABLE. La zone entre les boulevards fait 1499 m projetes ; a
        # l'echelle de MicroMacro — un personnage de 5 mm sur une affiche de
        # 75 cm, soit 1/150e de la largeur — une ville tient dans 255 m. La zone
        # complete represente donc 35 affiches. Augmenter la resolution n'y
        # change rien : la taille du personnage sur le papier est un RAPPORT,
        # elle vaut 0,9 mm a 8000 px comme a 100000 px.
        clat, clon = centre_du_lieu(args.osm, args.centre)
        mlat, mlon = M_PAR_DEG_LAT, m_par_deg_lon(clat)
        demi = args.cote / 2.0
        bbox = [round(clat - demi / mlat, 6), round(clon - demi / mlon, 6),
                round(clat + demi / mlat, 6), round(clon + demi / mlon, 6)]
        proj = 1.414 * args.cote      # un carre au sol vu a 45 deg d'azimut
        print(f"[bbox] coeur jouable centre sur {args.centre}")
        print(f"[bbox] {args.cote:.0f} x {args.cote:.0f} m au sol, "
              f"{proj:.0f} m projetes")
        print(f"[bbox] un personnage de 1,70 m fera {1.7 / proj * 750:.1f} mm "
              f"sur une affiche de 75 cm (MicroMacro : ~5 mm)")
        print(f"[bbox] lat {bbox[0]:.6f} .. {bbox[2]:.6f}")
        print(f"[bbox] lon {bbox[1]:.6f} .. {bbox[3]:.6f}")
        if not args.dry_run:
            cfg["zone"]["bbox"] = bbox
            cfg["zone"]["coeur"] = {"centre": args.centre, "cote_m": args.cote}
            cfg["import"]["source_osm"] = str(args.osm.relative_to(ROOT))
            CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
            print(f"[bbox] -> {CONFIG}")
        return 0

    noms = [n for n in cfg["zone"]["limites"] if "(" not in n]
    noms += cfg["zone"]["reperes_centraux"]
    points, bounds, n_voies = noeuds_des_voies_nommees(args.osm, noms)
    if not points:
        sys.exit("Aucune des limites nommees n'a ete trouvee dans l'extrait.")

    lat0, lon0, lat1, lon1 = englobe(points)
    mlat, mlon = M_PAR_DEG_LAT, m_par_deg_lon((lat0 + lat1) / 2)
    marge = args.marge if args.marge is not None else cfg["zone"]["marge_m"]
    d_lat, d_lon = marge / mlat, marge / mlon
    bbox = [round(lat0 - d_lat, 6), round(lon0 - d_lon, 6),
            round(lat1 + d_lat, 6), round(lon1 + d_lon, 6)]

    print(f"[bbox] {n_voies} voies nommees retenues, {len(points)} noeuds")
    print(f"[bbox] reperes seuls   : {(lon1-lon0)*mlon:7.0f} m x {(lat1-lat0)*mlat:7.0f} m")
    print(f"[bbox] avec {marge:.0f} m de marge : "
          f"{(bbox[3]-bbox[1])*mlon:7.0f} m x {(bbox[2]-bbox[0])*mlat:7.0f} m")
    print(f"[bbox] lat {bbox[0]:.6f} .. {bbox[2]:.6f}")
    print(f"[bbox] lon {bbox[1]:.6f} .. {bbox[3]:.6f}")

    if bounds:
        debords = {
            "sud":   (bounds[0] - bbox[0]) * mlat,
            "nord":  (bbox[2] - bounds[2]) * mlat,
            "ouest": (bounds[1] - bbox[1]) * mlon,
            "est":   (bbox[3] - bounds[3]) * mlon,
        }
        manque = {k: v for k, v in debords.items() if v > 0.5}
        if manque:
            print("[bbox] ATTENTION : l'extrait ne couvre pas toute la bbox.")
            for cote, m in sorted(manque.items(), key=lambda kv: -kv[1]):
                print(f"[bbox]   il manque {m:5.0f} m au {cote}")
            print("[bbox] la marge sera rognee de ce cote. Pour l'eviter, "
                  "retelecharger un extrait plus large.")
        else:
            print("[bbox] l'extrait couvre toute la bbox, marge comprise.")

    if args.dry_run:
        print("[bbox] --dry-run : config.json inchange")
        return 0

    cfg["zone"]["bbox"] = bbox
    cfg["import"]["source_osm"] = str(args.osm.relative_to(ROOT))
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(f"[bbox] -> {CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
