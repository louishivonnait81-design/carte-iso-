#!/usr/bin/env python3
"""Habillage des tuiles par l'API Gemini image.

    python stylize.py --tiles tiles/ --out styled/ --budget-eur 5

Pour chaque tuile, dans l'ordre de lecture, envoie :
    REF_01 (style de trait), [REF_02 (architecture castraise)],
    la tuile lignes, la tuile _sem,
    puis les voisines DEJA stylisees : gauche, puis haut.

Cache sur disque, reprise apres interruption, retries avec backoff, plafond de
depense. Une tuile deja stylisee n'est jamais ecrasee sans --force.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from gemini import (DEFAULT_MODEL, Budget, GeminiError, Pricing,  # noqa: E402
                    generate_image, load_client)

ROOT = Path(__file__).resolve().parent
REF01 = ROOT / "assets" / "REF_01_style.png"
REF02 = ROOT / "assets" / "REF_02_castres.png"
PROMPT = ROOT / "prompts" / "stylize_v2.md"

SECTION_RE = re.compile(r"<!--\s*@section\s+(\w+)\s*-->")
WATER_RGB = (102, 158, 229)      # bleu semantique tel qu'il ressort du rendu sRGB


# --------------------------------------------------------------------------
# Gabarit de prompt
# --------------------------------------------------------------------------

def load_sections(path: Path) -> dict[str, str]:
    """Decoupe le gabarit en sections `<!-- @section nom -->`."""
    text = path.read_text(encoding="utf-8")
    sections, name, buf = {}, None, []
    for line in text.splitlines():
        match = SECTION_RE.search(line)
        if match:
            if name:
                sections[name] = "\n".join(buf).strip()
            name, buf = match.group(1), []
        elif name:
            buf.append(line)
    if name:
        sections[name] = "\n".join(buf).strip()
    missing = {"base", "architecture", "left", "top"} - sections.keys()
    if missing:
        raise SystemExit(f"Sections manquantes dans {path} : {sorted(missing)}")
    return sections


def render_prompt(sections: dict[str, str], roles: list[str], parts: list[str]) -> str:
    """Assemble le prompt et remplace les variables par les vrais numeros d'image."""
    mapping: dict[str, str] = {}
    for index, role in enumerate(roles, start=1):
        mapping[role] = f"image {index}"
        mapping[role.capitalize()] = f"Image {index}"
    text = "\n\n".join(sections[p] for p in parts)
    for key, value in mapping.items():
        text = text.replace("{" + key + "}", value)
    leftovers = re.findall(r"\{(\w+)\}", text)
    if leftovers:
        raise SystemExit(f"Variables non resolues dans le prompt : {sorted(set(leftovers))}")
    return text


# --------------------------------------------------------------------------
# References au carre
# --------------------------------------------------------------------------

def squared(path: Path) -> Path:
    """Copie de l'image completee en carre par des marges blanches.

    Gemini calque le format de sortie sur celui des images recues : deux
    references en paysage donnent une tuile en paysage (mesure : 1,84 pour des
    references a 1,83). Une reference carree ne laisse aucune ambiguite.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(path)
    except UnidentifiedImageError:      # fichier factice (tests) : renvoye tel quel
        return path
    with img:
        if img.width == img.height:
            return path
        side = max(img.size)
        out_dir = path.parent / "square"
        out_dir.mkdir(exist_ok=True)
        out = out_dir / f"{path.stem}_sq.png"
        if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
            return out
        canvas = Image.new("RGB", (side, side), "white")
        canvas.paste(img.convert("RGB"), ((side - img.width) // 2, (side - img.height) // 2))
        canvas.save(out)
        return out


# --------------------------------------------------------------------------
# Detection d'eau dans la tuile semantique
# --------------------------------------------------------------------------

def has_water(sem_path: Path, tolerance: int = 40) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    import numpy as np

    with Image.open(sem_path) as img:
        arr = np.asarray(img.convert("RGB").resize((256, 256)), dtype=np.int16)
    return bool((np.abs(arr - np.array(WATER_RGB, dtype=np.int16)).max(axis=2) < tolerance).any())


# --------------------------------------------------------------------------
# Une tuile
# --------------------------------------------------------------------------

@dataclass
class Job:
    name: str
    roles: list[str]
    images: list[Path]
    prompt: str

    def cache_key(self, model: str, aspect: str, size: str) -> str:
        h = hashlib.sha256()
        h.update(f"{model}|{aspect}|{size}|".encode())
        h.update(self.prompt.encode())
        for path in self.images:
            h.update(hashlib.sha256(path.read_bytes()).digest())
        return h.hexdigest()


def load_notes(tiles_dir: Path) -> dict[str, list[dict]]:
    """tiles/notes.json, produit par scripts/tile_notes.py (facultatif)."""
    path = tiles_dir / "notes.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_job(tile: dict, tiles_dir: Path, out_dir: Path, sections: dict[str, str],
              use_ref02: bool, water_mode: str, notes: dict[str, list[dict]] | None = None) -> Job:
    line = tiles_dir / tile["line"]
    sem = tiles_dir / tile["semantic"]
    for path in (line, sem):
        if not path.exists():
            raise SystemExit(f"Tuile de squelette manquante : {path}")

    roles, images = ["ref01"], [squared(REF01)]
    if use_ref02:
        roles.append("ref02")
        images.append(squared(REF02))
    roles += ["lines", "sem"]
    images += [line, sem]

    for side in ("left", "top"):
        neighbour = tile["neighbours"].get(side)
        if not neighbour:
            continue
        styled = out_dir / f"{neighbour}.png"
        if styled.exists():
            roles.append(side)
            images.append(styled)

    water = water_mode == "on" or (water_mode == "auto" and has_water(sem))
    parts = ["base", "architecture"]
    entries = (notes or {}).get(tile["name"], [])
    if entries and "notes" in sections:
        parts.append("notes")
    if water and "water" in sections:
        parts.append("water")
    if use_ref02 and "ref02" in sections:
        parts.append("ref02")
    parts += [r for r in ("left", "top") if r in roles]

    filled = dict(sections)
    if entries and "notes" in sections:
        from tile_notes import format_notes
        filled["notes"] = sections["notes"].replace("{notes_list}", format_notes(entries))
    return Job(name=tile["name"], roles=roles, images=images,
               prompt=render_prompt(filled, roles, parts))


# --------------------------------------------------------------------------
# Boucle principale
# --------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tiles", type=Path, default=ROOT / "tiles", help="dossier des squelettes")
    p.add_argument("--out", type=Path, default=ROOT / "styled", help="dossier de sortie")
    p.add_argument("--model", default=DEFAULT_MODEL, help="modele image Gemini")
    p.add_argument("--image-size", default="2K", choices=["1K", "2K", "4K"])
    p.add_argument("--aspect-ratio", default="1:1")
    p.add_argument("--temperature", type=float, default=0.35,
                   help="plus bas = tuiles plus semblables entre elles")
    p.add_argument("--seed", type=int, default=1789,
                   help="graine fixe : meme entree, meme sortie")
    p.add_argument("--budget-eur", type=float, default=5.0,
                   help="plafond de depense cumulee, en euros")
    p.add_argument("--water", choices=["auto", "on", "off"], default="auto",
                   help="ajouter la legende 'bleu = eau' au prompt")
    p.add_argument("--ref02", choices=["auto", "on", "off"], default="auto",
                   help="joindre assets/REF_02_castres.png")
    p.add_argument("--only", help="ne traiter que ces tuiles, ex. 'tile_0_0,tile_0_1'")
    p.add_argument("--limit", type=int, default=None, help="s'arreter apres N tuiles")
    p.add_argument("--retries", type=int, default=4)
    p.add_argument("--force", action="store_true", help="re-styliser meme si la sortie existe")
    p.add_argument("--dry-run", action="store_true",
                   help="ecrire les prompts dans out/prompts/ sans appeler l'API")
    args = p.parse_args()

    index_path = args.tiles / "index.json"
    if not index_path.exists():
        sys.exit(f"{index_path} introuvable : lancer `make render` d'abord.")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    tiles = {t["name"]: t for t in index["tiles"]}

    if not REF01.exists():
        sys.exit(f"Reference de style manquante : {REF01}")
    use_ref02 = args.ref02 == "on" or (args.ref02 == "auto" and REF02.exists())
    if args.ref02 == "on" and not REF02.exists():
        sys.exit(f"--ref02 on mais {REF02} est absent.")

    sections = load_sections(PROMPT)
    notes = load_notes(args.tiles)
    if not notes:
        print("[notes] tiles/notes.json absent : lancer scripts/tile_notes.py pour "
              "nommer les lieux de chaque tuile dans le prompt.")
    args.out.mkdir(parents=True, exist_ok=True)

    wanted = set(args.only.split(",")) if args.only else None
    order = [n for n in index["render_order"] if wanted is None or n in wanted]
    if args.limit:
        order = order[:args.limit]

    pricing = Pricing.load(args.model)
    if not pricing.verified:
        print("[cout] ATTENTION : tarifs de pricing.json non verifies aupres de la doc "
              "officielle. Les montants ci-dessous sont indicatifs.")
    budget = Budget.load(args.out / ".budget.json", args.budget_eur)
    print(f"[cout] deja engage : {budget.spent_eur:.2f} EUR sur {budget.limit_eur:.2f} EUR "
          f"({budget.calls} appels)")

    client = None if args.dry_run else load_client()
    done = 0

    for name in order:
        out_png = args.out / f"{name}.png"
        meta_path = args.out / f"{name}.json"
        job = build_job(tiles[name], args.tiles, args.out, sections, use_ref02, args.water, notes)
        key = job.cache_key(args.model, args.aspect_ratio, args.image_size)

        if out_png.exists() and not args.force:
            old = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            same = old.get("cache_key") == key
            print(f"[{name}] deja stylisee, ignoree"
                  + ("" if same else "  (entrees modifiees depuis : --force pour refaire)"))
            continue

        refs = " + ".join(f"{i}:{r}" for i, r in enumerate(job.roles, 1))
        print(f"[{name}] {len(job.images)} images ({refs})")

        if args.dry_run:
            prompts_dir = args.out / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            (prompts_dir / f"{name}.txt").write_text(job.prompt, encoding="utf-8")
            print(f"    dry-run -> {prompts_dir / f'{name}.txt'}")
            continue

        budget.check(pricing.estimate_eur())
        result = generate_image(client, job.prompt, job.images, model=args.model,
                                aspect_ratio=args.aspect_ratio, image_size=args.image_size,
                                temperature=args.temperature, seed=args.seed,
                                retries=args.retries)
        cost = pricing.cost_eur(result.usage)
        budget.record(name, cost, result.usage)

        out_png.write_bytes(result.png)
        meta_path.write_text(json.dumps({
            "tile": name, "model": args.model, "cache_key": key,
            "roles": job.roles, "inputs": [str(p.relative_to(ROOT)) for p in job.images],
            "image_size": args.image_size, "aspect_ratio": args.aspect_ratio,
            "temperature": args.temperature, "seed": args.seed,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cost_eur": round(cost, 4), "cumulative_eur": round(budget.spent_eur, 4),
        }, indent=2), encoding="utf-8")

        print(f"    -> {out_png}  {cost:.3f} EUR  (cumul {budget.spent_eur:.2f} EUR)")
        done += 1

    print(f"[fin] {done} tuiles generees, cumul {budget.spent_eur:.2f} EUR")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GeminiError as exc:
        raise SystemExit(f"Erreur : {exc}")
