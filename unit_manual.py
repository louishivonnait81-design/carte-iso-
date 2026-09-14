"""Prepare une UNITE a coller dans le modele, et reprend le dessin qui revient.

    python unit_manual.py export u83180702
    python unit_manual.py import u83180702 dessin.png
    python unit_manual.py status

Deux differences avec le mode tuile, et elles decoulent l'une de l'autre.

Le prompt est court : il n'a plus a parler de position, de cadrage de tuile ni de
ce qui existe ailleurs sur la carte. Le compositeur place le dessin, donc le
modele n'a plus que deux contraintes — garder la silhouette et garder le cadre —
et une liste de ce qu'il faut poser dessus.

Et l'image partie au modele est CARREE. Les modeles d'image recopient le rapport
de forme de leur entree : une unite de 1423x1673 revenait avec quelques pour cent
d'ecart, et remettre ce dessin a l'echelle de sa boite l'aurait deforme. L'unite
est donc centree sur un carre blanc, et l'import redecoupe exactement la fenetre
d'origine. Le decalage est enregistre dans meta.json, pas recalcule.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
UNITS = ROOT / "units"
DRAWN = ROOT / "drawn"
OUT = ROOT / "manual_units"
REF01 = ROOT / "assets" / "REF_01_style.png"
TEMPLATE = ROOT / "prompts" / "unit.md"
RANGEES = ROOT / "prompts" / "rangees.md"


def load_index() -> dict:
    path = UNITS / "index.json"
    if not path.exists():
        raise SystemExit(f"{path} introuvable : lancer `make units` d'abord.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_fiches() -> dict[str, str]:
    """Fiches de RANGEE, indexees par le motif cherche dans le nom OSM.

    Pas celles de prompts/lieux.md : une fiche de lieu decrit un endroit vu
    d'ensemble et renvoie a "image 3", qui n'existe pas dans le prompt d'une
    unite. Une fiche de rangee dit ce que porte une facade, et rien d'autre.
    """
    if not RANGEES.exists():
        return {}
    fiches = {}
    for line in RANGEES.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- \*\*(.+?)\*\*\s*:\s*(.+)", line)
        if m:
            fiches[m.group(1).lower()] = m.group(2).strip()
    return fiches


def note_for(entry: dict, fiches: dict[str, str], names: dict[int, str]) -> str:
    """Fiches a joindre : celles des batiments nommes de l'unite, et celle de la
    place qu'elle borde.

    La seconde compte autant que la premiere. Aucun batiment de la place Jean
    Jaures ne porte son nom dans OSM, mais c'est elle qui dit que leur
    rez-de-chaussee est une arcade continue. render_units calcule quelles unites
    la bordent — sommets a moins de trois metres du polygone `place=square` — et
    l'ecrit dans "faces".
    """
    seen = []
    labels = [(names.get(wid) or "") for wid in entry["way_ids"]]
    labels += entry.get("faces", [])
    for name in labels:
        name = name.lower()
        if not name:
            continue
        for pattern, text in fiches.items():
            if pattern in name and text not in seen:
                seen.append(text)
    if not seen:
        return ""
    body = "\n".join(f"  {t}" for t in seen)
    return ("\n\nWHAT THIS ROW REALLY IS. Draw it as described here; this description "
            "was written from a photograph and wins over the general rules above.\n"
            + body + "\n")


def squared(image: Image.Image) -> tuple[Image.Image, tuple[int, int, int]]:
    """Centre l'image sur un carre blanc. Renvoie (carre, (offset_x, offset_y, cote))."""
    side = max(image.size)
    canvas = Image.new("L", (side, side), 255)
    ox, oy = (side - image.width) // 2, (side - image.height) // 2
    canvas.paste(image, (ox, oy))
    return canvas, (ox, oy, side)



# --------------------------------------------------------------------------
# Recalage du dessin sur la silhouette
# --------------------------------------------------------------------------

# Bornes du recalage. Elles sont etroites A DESSEIN : le placement de l'unite
# sur la carte vient de Blender et ne doit jamais dependre du dessin. Ce qu'on
# corrige ici est l'erreur d'echelle du modele A L'INTERIEUR de sa propre
# fenetre, mesuree sur les quatre premieres unites : il dessine le volume 3 a
# 21 % plus grand que celui qu'on lui donne, et le debord part vers le bas, donc
# le masque lui coupe le rez-de-chaussee — c'est-a-dire l'arcade.
FIT_SCALES = (0.86, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 1.00, 1.02)
FIT_SHIFT = 0.12          # decalage maximal, en fraction du cote
FIT_MIN_GAIN = 0.01       # en deca, on ne touche a rien


def filled_silhouette(gray: "Image.Image"):
    """Surface pleine du dessin : tout ce qui ne communique pas avec le bord."""
    import numpy as np
    from collections import deque

    white = np.asarray(gray) > 200
    h, w = white.shape
    seen = np.zeros_like(white)
    queue = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white[y, x] and not seen[y, x]:
                seen[y, x] = True
                queue.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if white[y, x] and not seen[y, x]:
                seen[y, x] = True
                queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                queue.append((ny, nx))
    return ~seen


def _iou(a, b) -> float:
    return float((a & b).sum() / max(1, (a | b).sum()))


def fit_to_mask(art: "Image.Image", mask: "Image.Image", step: int = 4):
    """Cale le dessin sur la silhouette Blender. Renvoie (dessin, rapport).

    Cherche l'echelle et le decalage qui maximisent le recouvrement entre la
    surface pleine du dessin et le masque. La recherche se fait sur une version
    reduite — au pixel pres, elle ne changerait rien et couterait cent fois plus.

    Le recalage n'est applique que s'il gagne vraiment : sous FIT_MIN_GAIN, le
    dessin est rendu tel quel. Un recalage qui n'apporte rien introduirait un
    reechantillonnage pour rien.
    """
    import numpy as np

    w, h = art.size
    sw, sh = max(8, w // step), max(8, h // step)
    ref = np.asarray(mask.resize((sw, sh), Image.NEAREST)) > 128
    base = filled_silhouette(art.resize((sw, sh), Image.LANCZOS))
    before = _iou(base, ref)

    best = (before, 1.0, 0, 0)
    span_x, span_y = int(sw * FIT_SHIFT), int(sh * FIT_SHIFT)
    for scale in FIT_SCALES:
        nw, nh = max(4, int(sw * scale)), max(4, int(sh * scale))
        shrunk = np.asarray(Image.fromarray((base * 255).astype(np.uint8))
                            .resize((nw, nh), Image.NEAREST)) > 128
        for dy in range(-span_y, span_y + 1, 2):
            for dx in range(-span_x, span_x + 1, 2):
                y0, x0 = (sh - nh) // 2 + dy, (sw - nw) // 2 + dx
                ys, xs = max(0, y0), max(0, x0)
                ye, xe = min(sh, y0 + nh), min(sw, x0 + nw)
                if ye <= ys or xe <= xs:
                    continue
                canvas = np.zeros((sh, sw), bool)
                canvas[ys:ye, xs:xe] = shrunk[ys - y0:ye - y0, xs - x0:xe - x0]
                score = _iou(canvas, ref)
                if score > best[0]:
                    best = (score, scale, dx * step, dy * step)

    after, scale, dx, dy = best
    report = {"iou_before": round(before, 3), "iou_after": round(after, 3),
              "scale": scale, "dx": dx, "dy": dy, "applied": False}
    if after - before < FIT_MIN_GAIN:
        return art, report

    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    canvas = Image.new("L", (w, h), 255)
    canvas.paste(art.resize((nw, nh), Image.LANCZOS),
                 ((w - nw) // 2 + dx, (h - nh) // 2 + dy))
    report["applied"] = True
    return canvas, report


def build_prompt(entry: dict, note: str) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text[text.index("-->") + 3:].lstrip("\n")
    return text.format(ref01=1, lines=2, note=note).rstrip() + "\n"


def export(name: str, index: dict, extra_note: str, force: bool) -> Path:
    entry = next((e for e in index["units"] if e["name"] == name), None)
    if entry is None:
        raise SystemExit(f"Unite inconnue : {name}")
    if not REF01.exists():
        raise SystemExit(f"{REF01} introuvable.")

    folder = OUT / name
    if folder.exists():
        if not force:
            raise SystemExit(f"{folder} existe deja : --force pour la refaire.")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    lines = Image.open(UNITS / entry["line"]).convert("L")
    square, (ox, oy, side) = squared(lines)
    shutil.copy(REF01, folder / "1_ref01.png")
    square.save(folder / "2_lines.png")

    names = {int(k): v for k, v in index.get("names", {}).items()}
    fiche = note_for(entry, load_fiches(), names)
    note = fiche + (f"\n\n{extra_note.strip()}\n" if extra_note else "")
    (folder / "prompt.txt").write_text(build_prompt(entry, note), encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps(
        {"unit": name, "pad": [ox, oy], "square": side,
         "size": [entry["w"], entry["h"]], "box": [entry["x"], entry["y"]]},
        indent=2), encoding="utf-8")

    print(f"[unite] {folder}")
    print(f"     image 1 : 1_ref01.png   REF_01 — style de trait")
    print(f"     image 2 : 2_lines.png   l'unite, centree sur un carre de {side} px")
    print(f"     la fenetre utile est {entry['w']}x{entry['h']} px a ({ox}, {oy})")
    if fiche:
        print("     une fiche de lieu est jointe au prompt")
    if extra_note:
        print("     une consigne libre est jointe au prompt")
    return folder


def import_drawing(name: str, source: Path, allow_nonsquare: bool,
                   fit: bool = True) -> Path:
    meta_path = OUT / name / "meta.json"
    if not meta_path.exists():
        raise SystemExit(f"{meta_path} introuvable : exporter l'unite d'abord.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    art = Image.open(source).convert("L")
    if art.width != art.height and not allow_nonsquare:
        raise SystemExit(
            f"{source} n'est pas carree ({art.width}x{art.height}). Le modele a "
            f"recadre : refaire, ou forcer avec --allow-nonsquare.")

    side = meta["square"]
    if art.size != (side, side):
        art = art.resize((side, side), Image.LANCZOS)
    ox, oy = meta["pad"]
    w, h = meta["size"]
    cropped = art.crop((ox, oy, ox + w, oy + h))

    if fit:
        mask = Image.open(UNITS / f"{name}_mask.png").convert("L")
        if mask.size != (w, h):
            mask = mask.resize((w, h), Image.NEAREST)
        cropped, report = fit_to_mask(cropped, mask)
        verdict = (f"echelle {report['scale']:.2f}, decalage "
                   f"({report['dx']:+d}, {report['dy']:+d})" if report["applied"]
                   else "laisse tel quel")
        print(f"[unite] recalage : IoU {report['iou_before']:.3f} -> "
              f"{report['iou_after']:.3f}  ({verdict})")

    DRAWN.mkdir(exist_ok=True)
    out = DRAWN / f"{name}.png"
    cropped.save(out)
    print(f"[unite] {source.name} -> {out}  {cropped.width}x{cropped.height}")
    return out


def status(index: dict) -> None:
    done = sorted(p.stem for p in DRAWN.glob("*.png")) if DRAWN.exists() else []
    total = len(index["units"])
    print(f"[unites] {len(done)}/{total} dessinees")
    for entry in sorted(index["units"], key=lambda e: e["order"]):
        mark = "##" if entry["name"] in done else ".."
        print(f"   {mark} {entry['name']:<12} {entry['w']:>5}x{entry['h']:<5} "
              f"{len(entry['way_ids'])} batiment(s)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export")
    e.add_argument("unit")
    e.add_argument("--note", default="", help="consigne libre ajoutee au prompt")
    e.add_argument("--force", action="store_true")

    i = sub.add_parser("import")
    i.add_argument("unit")
    i.add_argument("image", type=Path)
    i.add_argument("--allow-nonsquare", action="store_true")
    i.add_argument("--no-fit", action="store_true",
                   help="ne pas recaler le dessin sur la silhouette")

    sub.add_parser("status")
    args = p.parse_args()

    index = load_index()
    if args.cmd == "export":
        export(args.unit, index, args.note, args.force)
    elif args.cmd == "import":
        import_drawing(args.unit, args.image, args.allow_nonsquare,
                       fit=not args.no_fit)
    else:
        status(index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
