"""Mesure de JOUABILITE : un chemin est-il vraiment visible sur le dessin ?

Module sans Blender, donc testable seul. Il repond a une question precise, posee
par l'oeil et pas par les donnees : sur la carte finie, reste-t-il assez de sol
DEGAGE dans chaque ruelle pour y faire marcher quelqu'un ?

Deux choses se liguent contre une ruelle, et la largeur au sol n'en est qu'une :

1. LA LARGEUR. Elle se mesure par balayage. Un segment libre parcouru le long de
   X, borne par du bati des deux cotes, est la largeur d'une ruelle qui court
   NORD-SUD. Le long de Y, c'est une ruelle EST-OUEST. On ne mesure jamais sur
   les boites englobantes : une mesure faite ainsi avait annonce un gain nul sur
   un retrecissement pourtant reel de 1,2 m.

2. L'OMBRE PORTEE PAR LES MURS. La camera regarde du sud-ouest, a 60 degres
   au-dessus de l'horizon. Un mur de hauteur h cache derriere lui une bande de
   sol de h/tan(60) = 0,577 h de long, orientee vers le nord-est. Pour une
   ruelle nord-sud comme est-ouest, cela retire 0,408 h a sa largeur apparente.
   Avec les 9 m de hauteur par defaut, ce sont 3,7 m avales : une ruelle de 4 m
   n'a plus un seul pixel de sol visible, quelle que soit la resolution.

C'est pourquoi on mesure la LARGEUR VISIBLE, et non la largeur.
"""
from __future__ import annotations

import math

import numpy as np

# Largeur de sol degage, en metres, sous laquelle un chemin ne se joue pas. Un
# personnage fait 1,7 m de haut et environ 0,6 m de large ; il lui faut de quoi
# se tenir, croiser, et rester lisible entre deux traits de mur.
LARGEUR_JOUABLE_M = 2.5

PAS_M = 0.25


def rasteriser(triangles, hauteurs, boite, pas: float = PAS_M):
    """Rend une carte de hauteur du bati. `triangles` : liste de (p0,p1,p2) en
    2D ; `hauteurs` : la hauteur du batiment de chaque triangle.

    Renvoie (hauteur, x0, y0) ou `hauteur[j, i]` est la hauteur du bati sur la
    cellule, 0 la ou il n'y a rien. j suit Y vers le nord, i suit X vers l'est.
    """
    x0, y0, x1, y1 = boite
    nx = max(1, int(math.ceil((x1 - x0) / pas)))
    ny = max(1, int(math.ceil((y1 - y0) / pas)))
    hauteur = np.zeros((ny, nx), dtype=np.float32)

    for (p0, p1, p2), h in zip(triangles, hauteurs):
        xs = (p0[0], p1[0], p2[0])
        ys = (p0[1], p1[1], p2[1])
        i0 = max(0, int((min(xs) - x0) / pas))
        i1 = min(nx - 1, int((max(xs) - x0) / pas) + 1)
        j0 = max(0, int((min(ys) - y0) / pas))
        j1 = min(ny - 1, int((max(ys) - y0) / pas) + 1)
        if i1 < i0 or j1 < j0:
            continue
        ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
        px = x0 + (ii + 0.5) * pas
        py = y0 + (jj + 0.5) * pas
        # test barycentrique
        d = ((p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1]))
        if abs(d) < 1e-12:
            continue
        a = ((p1[1] - p2[1]) * (px - p2[0]) + (p2[0] - p1[0]) * (py - p2[1])) / d
        b = ((p2[1] - p0[1]) * (px - p2[0]) + (p0[0] - p2[0]) * (py - p2[1])) / d
        c = 1.0 - a - b
        dedans = (a >= -1e-9) & (b >= -1e-9) & (c >= -1e-9)
        if not dedans.any():
            continue
        bloc = hauteur[j0:j1 + 1, i0:i1 + 1]
        np.maximum(bloc, np.where(dedans, h, 0.0), out=bloc)
    return hauteur, x0, y0


def ombre(hauteur, pas: float = PAS_M, elevation_deg: float = 60.0):
    """Sol cache par les murs, vu du sud-ouest a `elevation_deg`.

    La camera est a l'azimut 315 : son rayon descend vers le nord-est. On balaie
    donc les diagonales i-j = cte dans ce sens. Le maximum courant se calcule
    d'un coup : l'ombre a l'etape n vaut max(h_m + m*chute) - n*chute, ce qui est
    un cumul de maximum et non une boucle.
    """
    ny, nx = hauteur.shape
    chute = pas * math.sqrt(2.0) * math.tan(math.radians(elevation_deg))
    cache = np.zeros_like(hauteur, dtype=bool)
    for d in range(-(ny - 1), nx):
        diag = np.diagonal(hauteur, offset=d)
        if diag.size == 0:
            continue
        n = np.arange(diag.size, dtype=np.float32)
        s = np.maximum.accumulate(diag + n * chute) - n * chute
        j0 = max(0, -d)
        i0 = max(0, d)
        idx = np.arange(diag.size)
        cache[j0 + idx, i0 + idx] = s > 1e-6
    return cache


def accessible(libre):
    """Sol libre RELIE au reste du monde, par remplissage depuis le bord.

    Une courette fermee au milieu d'un ilot n'est pas un chemin : personne ne
    peut y entrer, et la compter comme une ruelle invisible fausse la mesure. On
    ne garde donc que ce qui communique avec le bord de la zone.
    """
    from collections import deque
    ny, nx = libre.shape
    vu = np.zeros_like(libre, dtype=bool)
    pile = deque()
    for j in range(ny):
        for i in (0, nx - 1):
            if libre[j, i] and not vu[j, i]:
                vu[j, i] = True
                pile.append((j, i))
    for i in range(nx):
        for j in (0, ny - 1):
            if libre[j, i] and not vu[j, i]:
                vu[j, i] = True
                pile.append((j, i))
    while pile:
        j, i = pile.pop()
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = j + dj, i + di
            if 0 <= a < ny and 0 <= b < nx and libre[a, b] and not vu[a, b]:
                vu[a, b] = True
                pile.append((a, b))
    return vu


def segments(libre, axe: int, pas: float = PAS_M):
    """Largeurs des segments libres BORNES des deux cotes, le long d'un axe.

    axe=1 : balayage le long de X, donc largeurs des chemins NORD-SUD.
    axe=0 : balayage le long de Y, donc largeurs des chemins EST-OUEST.

    Renvoie une liste de (largeur_m, j, i_debut, i_fin) dans le repere du
    balayage. Un segment qui touche le bord du tableau est ecarte : sa largeur
    n'est pas mesuree, elle est tronquee.
    """
    tab = libre if axe == 1 else libre.T
    out = []
    for j, ligne in enumerate(tab):
        idx = np.flatnonzero(np.diff(ligne.astype(np.int8)))
        bords = np.concatenate(([0], idx + 1, [ligne.size]))
        for a, b in zip(bords[:-1], bords[1:]):
            if not ligne[a]:
                continue
            if a == 0 or b == ligne.size:
                continue                     # tronque par le bord du tableau
            out.append(((b - a) * pas, j, a, b))
    return out


def rapport(hauteur, pas: float = PAS_M, elevation_deg: float = 60.0,
            seuil: float = LARGEUR_JOUABLE_M):
    """Tout le diagnostic d'un coup. Renvoie un dict de chiffres.

    `part_jouable` est la part des traversees de ruelle dont le sol DEGAGE
    atteint le seuil. C'est le chiffre que l'on cherche a monter.
    """
    bati = hauteur > 0.01
    cache = ombre(hauteur, pas, elevation_deg)
    libre = accessible(~bati)
    visible = libre & ~cache

    res = {"pas_m": pas, "elevation_deg": elevation_deg, "seuil_m": seuil,
           "part_batie": float(bati.mean()),
           "part_sol_visible": float(visible.sum() / max(1, libre.sum()))}

    for axe, nom in ((1, "nord_sud"), (0, "est_ouest")):
        bruts = segments(libre, axe, pas)
        vus = segments(visible, axe, pas)
        # on ne garde que les traversees de ruelle : au-dela de 25 m ce n'est
        # plus une rue mais une place ou un jardin, toujours visible
        rue = np.array([w for w, *_ in bruts if w <= 25.0]) if bruts else np.zeros(0)
        # largeur degagee : pour chaque ligne, la somme des segments visibles
        # tombant dans la traversee
        degage = _degage(libre, visible, axe, pas)
        degage = np.array([w for w in degage if w is not None]) if degage else np.zeros(0)
        res[nom] = {
            "traversees": int(rue.size),
            "largeur_mediane_m": float(np.median(rue)) if rue.size else 0.0,
            "largeur_p10_m": float(np.percentile(rue, 10)) if rue.size else 0.0,
            "degage_median_m": float(np.median(degage)) if degage.size else 0.0,
            "part_jouable": float((degage >= seuil).mean()) if degage.size else 0.0,
            "part_invisible": float((degage < 0.5).mean()) if degage.size else 0.0,
        }
        del vus
    return res


def _degage(libre, visible, axe: int, pas: float):
    """Pour chaque traversee de ruelle, la plus large bande de sol VISIBLE
    qu'elle contient. C'est cette bande, et elle seule, qui se joue."""
    lib = libre if axe == 1 else libre.T
    vis = visible if axe == 1 else visible.T
    out = []
    for ligne, vue in zip(lib, vis):
        idx = np.flatnonzero(np.diff(ligne.astype(np.int8)))
        bords = np.concatenate(([0], idx + 1, [ligne.size]))
        for a, b in zip(bords[:-1], bords[1:]):
            if not ligne[a] or a == 0 or b == ligne.size:
                continue
            if (b - a) * pas > 25.0:
                continue
            bande = vue[a:b]
            if not bande.any():
                out.append(0.0)
                continue
            # plus longue suite de cellules visibles dans la traversee
            meilleur = courant = 0
            for val in bande:
                courant = courant + 1 if val else 0
                meilleur = max(meilleur, courant)
            out.append(meilleur * pas)
    return out
