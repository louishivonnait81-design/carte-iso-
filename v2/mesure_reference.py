"""Mesurer la REFERENCE : quel angle de camera une planche dessinee emploie-t-elle ?

    python3 v2/mesure_reference.py --test
    python3 v2/mesure_reference.py photo.jpg --zone 720 760 1450 1060
    python3 v2/mesure_reference.py photo.jpg --angles 14 -59

Ni Blender ni reseau : Pillow et numpy suffisent.

LE PRINCIPE. Dans une projection orthographique, deux directions du SOL
perpendiculaires entre elles tombent sur la page a des angles a1 et a2 tels que

        |tan(a1) x tan(a2)| = sin^2(elevation)

et cette relation ne depend PAS de l'orientation du batiment mesure. Il suffit
donc de trouver, sur une photo, les deux familles de droites d'un meme
batiment — par exemple les deux bords d'une toiture — pour en deduire la hauteur
de vue. La verticale, elle, reste verticale sur la page : c'est le controle qui
dit si la photo est droite.

COMMENT ON TROUVE LES FAMILLES. On tourne l'image d'un angle, on moyenne chaque
ligne, et on regarde si le profil obtenu est contraste : quand la rotation aligne
une famille de traits sur les lignes de l'image, le profil devient une suite de
creux nets. C'est une transformee de Radon du pauvre, et elle a un mérite sur
l'analyse de gradient : les croisements de traits ne l'abusent pas.

CE QU'IL FAUT SE MEFIER. Les plis du papier et l'eclairage font un pic a 0 degre
qui ecrase tout le reste ; d'ou le passe-haut avant la mesure, et le rejet de la
bande |angle| < 6 degres. Et le signe : la rotation de Pillow tourne dans l'autre
sens, l'angle rendu est l'oppose de l'angle du trait. `--test` verifie les deux.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

BANDE_MORTE = 6.0        # degres autour de 0 et de 90 : plis, trame, bord de page


def passe_haut(img: Image.Image, r: int = 11) -> Image.Image:
    a = np.asarray(img, dtype=np.float32)
    k = np.ones(2 * r + 1) / (2 * r + 1)
    b = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 0, a)
    b = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 1, b)
    return Image.fromarray(np.clip(128 + (a - b) * 2, 0, 255).astype(np.uint8))


def profil(img: Image.Image, pas: float = 0.5):
    """Nettete du profil pour chaque angle de rotation."""
    angles = np.arange(-89, 89, pas)
    out = []
    for a in angles:
        r = img.rotate(-a, resample=Image.BILINEAR, expand=True, fillcolor=128)
        A = np.asarray(r, dtype=np.float32)
        h, w = A.shape
        m = int(0.20 * min(h, w))
        A = A[m:h - m, m:w - m]
        if A.size == 0:
            out.append(0.0)
            continue
        p = A.mean(axis=1)
        p = p - np.convolve(p, np.ones(21) / 21, mode="same")
        out.append(float(np.var(p[12:-12])))
    return angles, np.convolve(np.array(out), np.ones(3) / 3, mode="same")


def familles(img: Image.Image, n: int = 4, ecart: float = 12.0):
    """Les n directions de traits les plus marquees, en degres, bande morte exclue.

    Positif = le trait descend vers la droite (l'axe y de l'image pointe en bas).
    """
    a, s = profil(passe_haut(img))
    garde = (np.abs(a) > BANDE_MORTE) & (np.abs(a) < 90 - BANDE_MORTE)
    a, s = a[garde], s[garde]
    res = []
    for i in np.argsort(-s):
        v = -a[i]                      # la rotation de Pillow inverse le signe
        if all(abs(v - p) > ecart for p, _ in res):
            res.append((v, s[i]))
        if len(res) == n:
            break
    haut = max(v for _, v in res) if res else 1.0
    return [(p, v / haut) for p, v in sorted(res)]


def elevation(a1: float, a2: float):
    """Hauteur de vue, en degres, a partir de deux directions du sol."""
    t = abs(math.tan(math.radians(a1)) * math.tan(math.radians(a2)))
    if t > 1.0:
        return None                    # pas deux directions d'un meme sol
    return math.degrees(math.asin(math.sqrt(t)))


def _planche(a1: float, a2: float, n: int = 800) -> Image.Image:
    img = Image.new("L", (n, n), 255)
    d = ImageDraw.Draw(img)
    for k in range(-70, 70):
        for a in (a1, a2):
            y = n // 2 + k * 30
            d.line([0, y, n, y + n * math.tan(math.radians(a))], fill=0, width=2)
    return img


def autotest() -> int:
    """Rejoue trois projections connues. Sans ce controle la mesure ne vaut rien :
    une premiere version, fondee sur le tenseur de structure, annoncait des
    familles a +-53 degres sur une planche tracee a +-30."""
    ok = True
    for elev, azimut in ((40, 21), (35, 45), (55, 30)):
        se = math.sin(math.radians(elev))
        t = math.tan(math.radians(azimut))
        a1 = math.degrees(math.atan(se * t))
        a2 = -math.degrees(math.atan(se / t))
        f = familles(_planche(a1, a2), n=2)
        mes = elevation(f[0][0], f[1][0])
        bon = mes is not None and abs(mes - elev) < 2.5
        ok &= bon
        print(f"  trace elevation {elev:2d} azimut {azimut:2d} -> familles "
              f"{a1:+6.1f} / {a2:+6.1f} ; mesure {f[0][0]:+6.1f} / {f[1][0]:+6.1f} "
              f"-> elevation {mes:5.1f}  {'OK' if bon else 'ECHEC'}")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("photo", nargs="?", type=Path)
    p.add_argument("--zone", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"),
                   help="n'analyser qu'un batiment : ses deux familles doivent "
                        "etre celles d'un MEME toit")
    p.add_argument("--angles", nargs=2, type=float, metavar=("A1", "A2"),
                   help="calculer l'elevation a partir de deux angles deja lus")
    p.add_argument("--verifier", nargs=2, type=float, metavar=("A1", "A2"),
                   help="tracer ces deux familles sur la zone, pour juger a l'oeil")
    p.add_argument("--sortie", type=Path, default=Path("verif.png"))
    p.add_argument("--test", action="store_true")
    args = p.parse_args()

    if args.test:
        return autotest()
    if args.angles:
        e = elevation(*args.angles)
        print(f"elevation = {e:.1f} deg" if e else
              "ces deux angles ne peuvent pas etre deux directions d'un meme sol")
        return 0
    if args.photo is None:
        p.error("donner une photo, ou --angles, ou --test")

    img = Image.open(args.photo).convert("L")
    if args.zone:
        img = img.crop(tuple(args.zone))
    print(f"{args.photo.name} {img.size}")

    if args.verifier:
        # LE JUGE, c'est l'oeil. La mesure propose plusieurs paires et une seule
        # est faite des deux bords d'un MEME toit ; aucune statistique ne le sait.
        v = img.convert("RGB").resize((img.size[0] * 2, img.size[1] * 2),
                                      Image.LANCZOS)
        d = ImageDraw.Draw(v)
        w, h = v.size
        for k in range(-80, 80):
            for a, col in zip(args.verifier, ((220, 0, 0), (0, 0, 220))):
                y = k * 60 + (0 if a == args.verifier[0] else 30)
                d.line([0, y, w, y + w * math.tan(math.radians(a))], fill=col, width=2)
        v.save(args.sortie)
        e = elevation(*args.verifier)
        print(f"  rouge {args.verifier[0]:+.1f}, bleu {args.verifier[1]:+.1f} -> "
              + (f"elevation {e:.1f} deg" if e else "paire impossible"))
        print(f"  -> {args.sortie}")
        return 0
    f = familles(img)
    for a, poids in f:
        print(f"  famille a {a:+6.1f} deg   force {poids:4.2f}")
    for i in range(len(f)):
        for j in range(i + 1, len(f)):
            e = elevation(f[i][0], f[j][0])
            if e is not None and f[i][0] * f[j][0] < 0:
                print(f"  paire {f[i][0]:+.1f} / {f[j][0]:+.1f} -> elevation {e:.1f} deg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
