"""Regroupement des batiments OSM en UNITES DE DESSIN.

Pourquoi ce module existe. Le pipeline precedent demandait au modele de
redessiner une tuile entiere a partir d'un squelette Blender. Mesure faite sur
tile_1_4, meilleur resultat obtenu apres six iterations : derive 0,461, et
34,8 % de l'encre tombant hors de toute emprise de batiment — deux maisons
entieres inventees sur la place. Le modele ne place pas la matiere ou on le lui
dit, quelles que soient les regles ajoutees au prompt.

On ne lui demande donc plus de la placer. Chaque unite est rendue seule, il la
redessine seule, et c'est nous qui la recollons a sa position exacte. La derive
de position devient nulle par construction : elle n'est plus une propriete du
dessin, mais du compositeur.

Reste a choisir l'unite. Un batiment a la fois donnerait 1397 dessins pour la
grille 7x4 — impraticable a la main, et faux architecturalement : dans une
vieille ville on ne dessine pas une maison, on dessine une rangee mitoyenne,
avec ses murs partages et sa ligne d'egout continue. Les batiments qui
partagent au moins un noeud OSM forment donc un groupe, decoupe ensuite pour
qu'aucune unite ne depasse `max_extent` metres.

Comptes mesures sur l'extrait de Castres, grille 7x4 de tuiles de 60 m :
    1397 batiments
     143 groupes mitoyens bruts (le plus grand : 81 batiments)
     437 unites apres decoupe a 45 m (le plus grand : 18, mediane 2)

Ce module est du Python pur : il s'importe depuis Blender comme depuis CPython.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field

# Cote maximal d'une unite, en metres. 45 m tient dans une tuile de 60 m de
# large a l'ecran, et laisse environ 45 px/m sur un rendu de 2048 px : de quoi
# dessiner des ouvertures de facade lisibles.
MAX_EXTENT_M = 45.0


@dataclass
class Building:
    """Un batiment OSM, deja projete en metres dans le repere local."""
    way_id: int
    points: list[tuple[float, float]]
    tags: dict
    nodes: list[int] = field(default_factory=list)

    @property
    def centroid(self) -> tuple[float, float]:
        n = len(self.points)
        return (sum(p[0] for p in self.points) / n,
                sum(p[1] for p in self.points) / n)


@dataclass
class Unit:
    """Une unite de dessin : une rangee mitoyenne, ou un batiment isole."""
    name: str
    way_ids: list[int]
    bbox: tuple[float, float, float, float]   # minx, miny, maxx, maxy en metres

    @property
    def size(self) -> tuple[float, float]:
        minx, miny, maxx, maxy = self.bbox
        return (maxx - minx, maxy - miny)

    @property
    def centroid(self) -> tuple[float, float]:
        minx, miny, maxx, maxy = self.bbox
        return ((minx + maxx) / 2, (miny + maxy) / 2)


def bbox_of(buildings: list[Building]) -> tuple[float, float, float, float]:
    pts = [p for b in buildings for p in b.points]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def _extent(buildings: list[Building]) -> float:
    minx, miny, maxx, maxy = bbox_of(buildings)
    return max(maxx - minx, maxy - miny)


def adjacency_groups(buildings: dict[int, Building]) -> list[list[int]]:
    """Groupe les batiments qui partagent au moins un noeud OSM.

    Le partage d'un noeud est la trace, dans les donnees, d'un mur mitoyen :
    deux facades qui se touchent ont ete saisies avec le meme point.
    """
    node_to_ways: dict[int, list[int]] = collections.defaultdict(list)
    for wid, b in buildings.items():
        for nid in b.nodes:
            node_to_ways[nid].append(wid)

    parent = {wid: wid for wid in buildings}

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for ways in node_to_ways.values():
        first = ways[0]
        for other in ways[1:]:
            ra, rb = find(first), find(other)
            if ra != rb:
                parent[ra] = rb

    groups: dict[int, list[int]] = collections.defaultdict(list)
    for wid in buildings:
        groups[find(wid)].append(wid)
    # tri stable : par plus petit way_id, pour que deux executions donnent le
    # meme ordre et donc les memes noms d'unites
    return [sorted(g) for _, g in sorted(groups.items(), key=lambda kv: min(kv[1]))]


def split_long_group(group: list[int], buildings: dict[int, Building],
                     max_extent: float) -> list[list[int]]:
    """Coupe une rangee trop longue en tranches, le long de son plus grand axe.

    Le plus grand groupe mitoyen de Castres compte 81 batiments et traverse
    plusieurs tuiles : le dessiner d'un bloc donnerait quelques pixels par
    metre. On le tranche donc, en gardant l'ordre le long de la rangee pour que
    chaque tranche reste un morceau continu de facade.
    """
    if len(group) == 1:
        return [group]
    members = [buildings[w] for w in group]
    if _extent(members) <= max_extent:
        return [group]

    minx, miny, maxx, maxy = bbox_of(members)
    axis = 0 if (maxx - minx) >= (maxy - miny) else 1
    ordered = sorted(group, key=lambda w: buildings[w].centroid[axis])

    slices: list[list[int]] = []
    current = [ordered[0]]
    for wid in ordered[1:]:
        trial = current + [wid]
        if _extent([buildings[w] for w in trial]) > max_extent:
            slices.append(current)
            current = [wid]
        else:
            current = trial
    slices.append(current)
    return slices


def unit_name(way_ids: list[int]) -> str:
    """Nom stable, lisible, et qui survit a un reordonnancement des donnees."""
    return f"u{min(way_ids)}"


def build_units(buildings: dict[int, Building],
                max_extent: float = MAX_EXTENT_M) -> list[Unit]:
    units: list[Unit] = []
    for group in adjacency_groups(buildings):
        for part in split_long_group(group, buildings, max_extent):
            part = sorted(part)
            units.append(Unit(name=unit_name(part), way_ids=part,
                              bbox=bbox_of([buildings[w] for w in part])))
    units.sort(key=lambda u: u.name)
    return units


def units_touching(units: list[Unit],
                   bbox: tuple[float, float, float, float]) -> list[Unit]:
    """Unites dont l'emprise recoupe `bbox` — y compris a cheval sur le bord.

    Une rangee coupee par la frontiere d'une tuile appartient aux deux : elle
    est dessinee une fois et collee une fois, le compositeur travaillant sur la
    carte entiere et non tuile par tuile.
    """
    minx, miny, maxx, maxy = bbox
    out = []
    for u in units:
        a, b, c, d = u.bbox
        if a <= maxx and c >= minx and b <= maxy and d >= miny:
            out.append(u)
    return out
