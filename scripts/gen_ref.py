#!/usr/bin/env python3
"""Genere assets/REF_02_castres.png : le style de trait de REF_01, mais avec
l'architecture castraise.

    python scripts/gen_ref.py                 # une planche
    python scripts/gen_ref.py --variants 3    # trois propositions a comparer

Les variantes sortent dans assets/ref02_candidates/ ; on retient la bonne en la
copiant en assets/REF_02_castres.png (--accept N le fait).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gemini import (DEFAULT_MODEL, Budget, GeminiError, Pricing,  # noqa: E402
                    generate_image, load_client)

ROOT = Path(__file__).resolve().parents[1]
REF01 = ROOT / "assets" / "REF_01_style.png"
REF02 = ROOT / "assets" / "REF_02_castres.png"
PROMPT = ROOT / "prompts" / "ref02_castres.md"
CANDIDATES = ROOT / "assets" / "ref02_candidates"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--variants", type=int, default=2, help="nombre de propositions")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--image-size", default="2K", choices=["1K", "2K", "4K"])
    p.add_argument("--budget-eur", type=float, default=5.0)
    p.add_argument("--accept", type=int, default=None,
                   help="promouvoir la variante N en assets/REF_02_castres.png")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    CANDIDATES.mkdir(parents=True, exist_ok=True)

    if args.accept is not None:
        chosen = CANDIDATES / f"ref02_{args.accept:02d}.png"
        if not chosen.exists():
            sys.exit(f"Variante introuvable : {chosen}")
        if REF02.exists() and not args.force:
            sys.exit(f"{REF02} existe deja : --force pour la remplacer.")
        shutil.copyfile(chosen, REF02)
        print(f"[ref02] {chosen.name} -> {REF02}")
        return 0

    if not REF01.exists():
        sys.exit(f"Reference de style manquante : {REF01}")

    prompt = PROMPT.read_text(encoding="utf-8")
    pricing = Pricing.load(args.model)
    budget = Budget.load(CANDIDATES / ".budget.json", args.budget_eur)
    client = load_client()

    for i in range(1, args.variants + 1):
        out = CANDIDATES / f"ref02_{i:02d}.png"
        if out.exists() and not args.force:
            print(f"[ref02] {out.name} existe deja, ignoree")
            continue
        budget.check(pricing.estimate_eur())
        result = generate_image(client, prompt, [REF01], model=args.model,
                                aspect_ratio="1:1", image_size=args.image_size)
        cost = pricing.cost_eur(result.usage)
        budget.record(out.name, cost, result.usage)
        out.write_bytes(result.png)
        print(f"[ref02] {out}  {cost:.3f} EUR  (cumul {budget.spent_eur:.2f} EUR)")

    print("[ref02] choisir une variante puis : "
          "python scripts/gen_ref.py --accept N")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GeminiError as exc:
        raise SystemExit(f"Erreur : {exc}")
