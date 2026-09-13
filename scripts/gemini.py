"""Couche d'appel a l'API Gemini image + suivi du cout.

La cle est lue dans GEMINI_API_KEY et n'est jamais journalisee.

Le nom du modele n'est pas devine : la valeur par defaut peut etre remplacee par
--model ou GEMINI_IMAGE_MODEL, et `python scripts/gemini.py --list-models`
interroge l'API pour afficher les modeles image reellement disponibles sur la
cle utilisee. Les parametres image_config.aspect_ratio / image_size proviennent
du SDK officiel google-genai (types.ImageConfig).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")
ROOT = Path(__file__).resolve().parents[1]
PRICING_PATH = ROOT / "pricing.json"


class GeminiError(RuntimeError):
    pass


def load_client(api_key: str | None = None):
    from google import genai

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiError(
            "GEMINI_API_KEY absente. La definir dans l'environnement "
            "(export GEMINI_API_KEY=...), jamais dans le depot."
        )
    return genai.Client(api_key=key)


# --------------------------------------------------------------------------
# Cout
# --------------------------------------------------------------------------

@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class Pricing:
    eur_per_usd: float
    input_per_mtok_usd: float
    output_image_per_mtok_usd: float
    tokens_per_image_2k: int
    verified: bool

    @classmethod
    def load(cls, model: str, path: Path = PRICING_PATH) -> "Pricing":
        data = json.loads(path.read_text(encoding="utf-8"))
        rates = data["models"].get(model, data["models"]["default"])
        return cls(
            eur_per_usd=float(data["eur_per_usd"]),
            input_per_mtok_usd=float(rates["input_per_mtok_usd"]),
            output_image_per_mtok_usd=float(rates["output_image_per_mtok_usd"]),
            tokens_per_image_2k=int(rates["tokens_per_image_2k"]),
            verified=bool(data.get("verified", False)),
        )

    def cost_eur(self, usage: Usage) -> float:
        usd = (usage.input_tokens * self.input_per_mtok_usd
               + usage.output_tokens * self.output_image_per_mtok_usd) / 1e6
        return usd * self.eur_per_usd

    def estimate_eur(self, input_tokens: int = 3000) -> float:
        """Estimation a priori d'un appel, pour le garde-fou de budget."""
        return self.cost_eur(Usage(input_tokens=input_tokens,
                                   output_tokens=self.tokens_per_image_2k))


@dataclass
class Budget:
    """Garde-fou : refuse de depasser le plafond sans accord explicite."""

    limit_eur: float
    spent_eur: float = 0.0
    calls: int = 0
    state_path: Path | None = None
    history: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, state_path: Path, limit_eur: float) -> "Budget":
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return cls(limit_eur=limit_eur, spent_eur=float(data.get("spent_eur", 0.0)),
                       calls=int(data.get("calls", 0)), state_path=state_path,
                       history=data.get("history", []))
        return cls(limit_eur=limit_eur, state_path=state_path)

    def check(self, next_estimate_eur: float) -> None:
        if self.spent_eur + next_estimate_eur > self.limit_eur:
            raise GeminiError(
                f"Plafond de depense atteint : {self.spent_eur:.2f} EUR deja engages, "
                f"prochain appel estime a {next_estimate_eur:.2f} EUR, plafond "
                f"{self.limit_eur:.2f} EUR.\n"
                f"Relancer avec --budget-eur <montant> pour autoriser davantage."
            )

    def record(self, label: str, cost_eur: float, usage: Usage) -> None:
        self.spent_eur += cost_eur
        self.calls += 1
        self.history.append({"label": label, "cost_eur": round(cost_eur, 4),
                             "input_tokens": usage.input_tokens,
                             "output_tokens": usage.output_tokens})
        self.save()

    def save(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(
            {"spent_eur": round(self.spent_eur, 4), "calls": self.calls,
             "history": self.history}, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# Appel image
# --------------------------------------------------------------------------

@dataclass
class ImageResult:
    png: bytes
    usage: Usage
    model: str
    text: str = ""


def _mime(path: Path) -> str:
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp"}.get(path.suffix.lower(), "image/png")


def generate_image(client, prompt: str, images: list[Path], *, model: str = DEFAULT_MODEL,
                   aspect_ratio: str = "1:1", image_size: str = "2K",
                   temperature: float | None = None, seed: int | None = None,
                   retries: int = 4, base_delay: float = 4.0) -> ImageResult:
    """Un appel image, avec reprise exponentielle sur erreur transitoire.

    `temperature` basse et `seed` fixe reduisent la variabilite d'une tuile a
    l'autre : c'est le seul vrai levier de constance, et il n'existe pas dans
    l'interface web.
    """
    from google.genai import types

    contents: list = []
    for path in images:
        contents.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=_mime(path)))
    contents.append(prompt)

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=image_size),
        temperature=temperature,
        seed=seed,
    )

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.models.generate_content(model=model, contents=contents,
                                                      config=config)
            return _extract(response, model)
        except Exception as exc:  # noqa: BLE001 - on retente sur tout ce qui est transitoire
            last_error = exc
            if attempt >= retries or not _is_transient(exc):
                break
            delay = base_delay * (2 ** attempt) + random.uniform(0, 2.0)
            print(f"    ! {type(exc).__name__}: {_safe(exc)} — nouvelle tentative "
                  f"dans {delay:.0f} s ({attempt + 1}/{retries})")
            time.sleep(delay)
    raise GeminiError(f"Appel image echoue apres {retries + 1} tentatives : {_safe(last_error)}")


def _is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(s in text for s in ("429", "500", "502", "503", "504", "deadline",
                                   "unavailable", "timeout", "resource_exhausted",
                                   "internal", "connection"))


def _safe(exc: Exception | None) -> str:
    """Message d'erreur expurge de toute cle d'API."""
    text = str(exc) if exc else ""
    key = os.environ.get("GEMINI_API_KEY")
    return text.replace(key, "***") if key else text


def _extract(response, model: str) -> ImageResult:
    png, texts = None, []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in (getattr(content, "parts", None) or []):
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                png = png or inline.data
            if getattr(part, "text", None):
                texts.append(part.text)
    if png is None:
        raise GeminiError(
            "Reponse sans image. Texte renvoye : " + (" ".join(texts)[:400] or "(vide)"))

    meta = getattr(response, "usage_metadata", None)
    usage = Usage(
        input_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
        output_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
        total_tokens=int(getattr(meta, "total_token_count", 0) or 0),
    )
    return ImageResult(png=png, usage=usage, model=model, text=" ".join(texts))


def list_image_models(client) -> list[str]:
    names = []
    for model in client.models.list():
        actions = set(getattr(model, "supported_actions", None) or [])
        name = getattr(model, "name", "")
        if "image" in name.lower() or "generateImage" in actions:
            names.append(f"{name}  [{','.join(sorted(actions)) or '-'}]")
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verification de la connexion API Gemini.")
    parser.add_argument("--list-models", action="store_true",
                        help="lister les modeles image disponibles sur la cle")
    args = parser.parse_args()
    if args.list_models:
        for line in list_image_models(load_client()):
            print(line)
    else:
        parser.print_help()
