"""Ce qu'il y a reellement dans chaque tuile, d'apres les noms OSM.

    python scripts/tile_notes.py --tiles tiles/ --osm assets/castres.osm

Le prompt de base dit comment dessiner ; il ne dit jamais ce qu'il y a. Or le
modele connait Castres : nommer la cathedrale Saint-Benoit, la place Jean Jaures
ou une boulangerie l'amene a dessiner ce qui existe au lieu d'inventer.

Produit tiles/notes.json : pour chaque tuile, la liste des lieux nommes qui la
touchent (rues, places, edifices, cafes, commerces), avec leur position dans la
tuile (top-left, centre, bottom-right...) et, pour les lieux notables, la fiche de
prompts/lieux.md.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import TileGrid, latlon_to_xy, project  # noqa: E402
from osm_to_blend import Osm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# (tag, valeur) -> (libelle anglais, priorite ; 0 = en tete de liste)
KINDS = {
    ("place", "square"): ("square", 1),
    ("leisure", "park"): ("public garden", 1),
    ("leisure", "garden"): ("garden", 1),
    ("natural", "water"): ("river", 1),
    ("waterway", "riverbank"): ("river", 1),
    ("waterway", "river"): ("river", 1),
    ("bridge", "yes"): ("bridge", 1),
    ("man_made", "bridge"): ("bridge", 1),
    ("amenity", "place_of_worship"): ("church", 2),
    ("building", "church"): ("church", 2),
    ("building", "cathedral"): ("cathedral", 2),
    ("amenity", "townhall"): ("town hall", 2),
    ("amenity", "theatre"): ("theatre", 2),
    ("tourism", "museum"): ("museum", 2),
    ("historic", "*"): ("historic building", 2),
    ("tourism", "hotel"): ("hotel", 3),
    ("amenity", "school"): ("school", 3),
    ("amenity", "college"): ("school", 3),
    ("amenity", "marketplace"): ("covered market", 2),
    ("amenity", "cafe"): ("café", 4),
    ("amenity", "bar"): ("bar", 4),
    ("amenity", "restaurant"): ("restaurant", 4),
    ("amenity", "fast_food"): ("takeaway", 5),
    ("amenity", "pharmacy"): ("pharmacy", 4),
    ("amenity", "bank"): ("bank", 5),
    ("amenity", "fountain"): ("fountain", 1),
    ("amenity", "parking"): ("car park", 5),
    ("shop", "bakery"): ("bakery", 4),
    ("shop", "butcher"): ("butcher", 4),
    ("shop", "confectionery"): ("confectioner", 4),
    ("shop", "clothes"): ("clothes shop", 5),
    ("shop", "shoes"): ("shoe shop", 5),
    ("shop", "jewelry"): ("jeweller", 5),
    ("shop", "optician"): ("optician", 5),
    ("shop", "hairdresser"): ("hairdresser", 5),
    ("shop", "books"): ("bookshop", 4),
    ("shop", "newsagent"): ("newsagent", 5),
    ("shop", "florist"): ("florist", 4),
    ("shop", "*"): ("shop", 6),
    ("highway", "pedestrian"): ("pedestrian street", 3),
    ("highway", "*"): ("street", 3),
}
# Elements sans nom mais qui comptent sur une carte de jeu. tile_notes ne
# retenait que ce qui porte un name : la fontaine de la place Jean Jaures n'en a
# pas et n'a donc jamais ete signalee au modele, qui ne l'a pas dessinee.
UNNAMED = {
    ("amenity", "fountain"): ("public fountain", 1),
    ("amenity", "drinking_water"): ("drinking fountain", 3),
    ("historic", "memorial"): ("memorial", 2),
    ("historic", "monument"): ("monument", 2),
    ("tourism", "artwork"): ("public artwork", 2),
    ("amenity", "bicycle_parking"): ("bicycle stands", 5),
    ("amenity", "bench"): ("bench", 6),
    ("amenity", "post_box"): ("post box", 6),
    ("amenity", "telephone"): ("phone box", 6),
    ("amenity", "waste_basket"): ("litter bin", 6),
    ("highway", "street_lamp"): ("street lamp", 6),
}

IGNORE = {("highway", "bus_stop"), ("highway", "service"), ("highway", "footway"),
          ("highway", "path"), ("highway", "steps"), ("highway", "cycleway")}
MAX_PER_TILE = 18

# Devanture par type de commerce : ce qui rend une boutique reconnaissable au
# premier coup d'oeil, sans une seule lettre. C'est ce qui donnera aux enquetes
# de quoi s'accrocher — on ne cache pas un indice dans "un commerce", on le cache
# chez le boucher.
DEVANTURES = {
    "public fountain": "a stone basin fountain with a low rim, water spouting from "
                       "its centre, standing free on the paving",
    "drinking fountain": "a small cast-iron drinking fountain on a post",
    "bicycle stands": "a row of hoop stands with two or three bicycles locked to them",
    "memorial": "a carved stone memorial on a low plinth",
    "public artwork": "a sculpture on a plain plinth",
    "bakery": "wide window full of long loaves standing in baskets and round tarts on "
              "trays, a folding sign on the pavement",
    "butcher": "window with hanging hams and sausages on hooks above a tiled counter, "
               "a striped awning",
    "confectioner": "small bowed window with tiered stands of boxes and jars",
    "café": "pavement terrace of small round tables and bentwood chairs under a long "
            "awning, a waiter's till by the door",
    "bar": "narrow front with a few high tables outside, shutters folded back, crates "
           "of bottles stacked by the side door",
    "restaurant": "terrace with square tables and cloths, a blackboard easel by the "
                  "door, potted bay trees framing the entrance",
    "takeaway": "narrow counter opening onto the street, a queue rail, a rolled awning",
    "pharmacy": "sober front with a cross sign bracketed over the door and an orderly "
                "window of boxes on glass shelves",
    "clothes shop": "large plate-glass window with dressed mannequins and a rail, "
                    "a tall glass door",
    "shoe shop": "window of tiered shelves with single shoes displayed on each step",
    "jeweller": "small deep window behind a metal grille, velvet stands, a heavy door",
    "optician": "window with rows of spectacle frames on small stands",
    "hairdresser": "window showing mirrors, basins and swivel chairs inside",
    "bookshop": "window of stacked and fanned books, a trestle of second-hand books "
                "outside under the awning",
    "newsagent": "revolving rack of newspapers and postcards on the pavement",
    "florist": "flowers in zinc buckets spilling out onto the pavement, an open front",
    "shop": "plain shopfront with a canvas awning and a display window",
    "bank": "sober stone ground floor, tall barred windows, a cash machine set into "
            "the wall, no awning and no terrace",
    "hotel": "canopy over the entrance, a doorway with steps, shuttered windows above",
    "covered market": "large open hall with iron columns and a glazed roof, stalls "
                      "and crates under it",
}


def kind_of(tags: dict) -> tuple[str, int] | None:
    for key in ("place", "leisure", "natural", "waterway", "bridge", "man_made", "amenity",
                "tourism", "historic", "shop", "building", "highway"):
        if key not in tags:
            continue
        if (key, tags[key]) in IGNORE:
            return None
        if (key, tags[key]) in KINDS:
            return KINDS[(key, tags[key])]
        if (key, "*") in KINDS:
            return KINDS[(key, "*")]
    return None


def load_fiches(path: Path) -> list[tuple[re.Pattern, str]]:
    fiches = []
    if not path.exists():
        return fiches
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"-\s+\*\*(.+?)\*\*\s*:\s*(.+)", line)
        if m:
            fiches.append((re.compile(re.escape(m.group(1)), re.I), m.group(2).strip()))
    return fiches


def position_label(su: float, sv: float, tile_m: float) -> str:
    third = tile_m / 3.0
    col = "left" if su < -third / 2 else ("right" if su > third / 2 else "")
    row = "top" if sv > third / 2 else ("bottom" if sv < -third / 2 else "")
    return "-".join(p for p in (row, col) if p) or "centre"


def build_notes(index: dict, osm: Osm, fiches) -> dict[str, list[dict]]:
    g = TileGrid.build(
        index["grid"]["rows"], index["grid"]["cols"], index["tile"]["metres"],
        index["tile"]["pixels"], index["center"]["lat"], index["center"]["lon"],
        index["scene_origin"]["lat"], index["scene_origin"]["lon"],
        elevation_deg=index["camera"]["elevation_deg"],
    )
    tile_m = g.tile_m
    half_w, half_h = g.cols * tile_m / 2, g.rows * tile_m / 2

    def screen(nid: int):
        p = osm.nodes.get(nid)
        if p is None:
            return None
        x, y = latlon_to_xy(p[0], p[1], g.origin_lat, g.origin_lon)
        return project((x, y, 0.0), g.target, g.basis)

    # un element est note dans chaque tuile qu'un de ses noeuds touche
    per_tile: dict[str, dict[str, dict]] = defaultdict(dict)

    def densify(node_ids: list[int], step: float = 8.0):
        """Points ecran tous les `step` metres le long du chemin, noeuds compris."""
        pts = [s for s in (screen(n) for n in node_ids) if s is not None]
        out = []
        for a, b in zip(pts, pts[1:] or pts):
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) // step))
            out += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)]
        return out + pts[-1:]

    def add(name: str, tags: dict, node_ids: list[int],
            forced: tuple[str, int] | None = None) -> None:
        kind = forced or kind_of(tags)
        if kind is None:
            return
        label, prio = kind
        buckets: dict[tuple[int, int], list] = defaultdict(list)
        for su, sv in densify(node_ids):
            if abs(su) >= half_w or abs(sv) >= half_h:
                continue
            col = int((su + half_w) // tile_m)
            row = int((half_h - sv) // tile_m)
            buckets[(row, col)].append((su - (col - (g.cols - 1) / 2) * tile_m,
                                        sv - ((g.rows - 1) / 2 - row) * tile_m))
        is_street = label.endswith("street")
        desc = None if is_street else next((d for pat, d in fiches if pat.search(name)), None)
        for (row, col), pts in buckets.items():
            su = sum(p[0] for p in pts) / len(pts)
            sv = sum(p[1] for p in pts) / len(pts)
            tname = g.tile_name(row, col)
            entry = {"name": name, "kind": label, "position": position_label(su, sv, tile_m),
                     "priority": 0 if desc else prio}
            if desc:
                entry["description"] = desc
            # un meme nom (rue en plusieurs troncons, place + son parking)
            # n'apparait qu'une fois par tuile : l'entree la plus prioritaire reste
            previous = per_tile[tname].get(name)
            if previous is None or entry["priority"] < previous["priority"]:
                per_tile[tname][name] = entry

    def unnamed_label(tags: dict) -> tuple[str, int] | None:
        for key, value in tags.items():
            if (key, value) in UNNAMED:
                return UNNAMED[(key, value)]
        return None

    for nid, tags in osm.node_tags.items():
        if "name" in tags:
            add(tags["name"], tags, [nid])
        elif (label := unnamed_label(tags)):
            add(label[0], tags, [nid], forced=label)
    for wid, tags in osm.way_tags.items():
        if "name" in tags:
            add(tags["name"], tags, osm.ways[wid])
        elif (label := unnamed_label(tags)):
            add(label[0], tags, osm.ways[wid], forced=label)
    for tags, members in osm.relations:
        if "name" in tags:
            add(tags["name"], tags, [n for _, w in members if w in osm.ways for n in osm.ways[w]])

    # Un memorial et un bassin au meme endroit sont un seul monument : la vasque
    # de la statue de Jean Jaures est a 1 m de la statue, et les deux
    # apparaissaient comme deux lieux distincts.
    for tname, entries in per_tile.items():
        memorials = [e for e in entries.values()
                     if e["kind"] in {"historic building", "memorial", "monument"}]
        if memorials:
            for key in [k for k, e in entries.items()
                        if e["kind"] == "public fountain"
                        and any(m["position"] == e["position"] for m in memorials)]:
                del entries[key]

    notes = {}
    for tname, entries in per_tile.items():
        ordered = sorted(entries.values(), key=lambda e: (e["priority"], e["kind"], e["name"]))
        notes[tname] = ordered[:MAX_PER_TILE]
    return notes


def format_notes(entries: list[dict]) -> str:
    """Une devanture n'est decrite qu'a sa premiere occurrence dans la tuile :
    trois banques n'ont pas besoin de trois fois la meme phrase, et la place
    gagnee profite aux commerces suivants."""
    lines, described = [], set()
    for e in entries:
        anonymous = e["name"] == e["kind"]
        line = (f"- a {e['kind']} ({e['position']} of this tile)" if anonymous
                else f"- {e['name']} ({e['kind']}, {e['position']} of this tile)")
        detail = e.get("description")
        if not detail and e["kind"] not in described:
            detail = DEVANTURES.get(e["kind"])
            if detail:
                described.add(e["kind"])
        if detail:
            line += f": {detail}"
        elif e["kind"] in described:
            line += ", same shopfront"
        lines.append(line)
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tiles", type=Path, default=ROOT / "tiles")
    p.add_argument("--osm", type=Path, default=ROOT / "assets" / "castres.osm")
    p.add_argument("--fiches", type=Path, default=ROOT / "prompts" / "lieux.md")
    args = p.parse_args()

    index = json.loads((args.tiles / "index.json").read_text(encoding="utf-8"))
    osm = Osm.parse(args.osm)
    notes = build_notes(index, osm, load_fiches(args.fiches))
    out = args.tiles / "notes.json"
    out.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")

    for tname in index["render_order"]:
        entries = notes.get(tname, [])
        stars = sum(1 for e in entries if e.get("description"))
        print(f"[notes] {tname}: {len(entries):2d} lieux" + (f", {stars} fiches" if stars else ""))
    print(f"[notes] -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
