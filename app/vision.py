"""Claude calls: label reading (vision) and similar-wine suggestions."""
import base64
import io
import json
import logging
from typing import Any

import anthropic
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import settings
from .schemas import LabelInfo, SuggestionList

log = logging.getLogger(__name__)

# Server-side fallback if the main model declines a request (enabled by default).
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_MAX_SIDE = 1568  # Claude downsizes larger images anyway

LABEL_SYSTEM = """You are a sommelier and an expert at reading wine labels.
You are shown one or more phone photos of the SAME bottle (often crooked, with glare):
usually the front label, sometimes the back label or a detail (neck label, capsule).
Combine the information from all photos.

Rules:
- The back label often names the actual producer ("bottled by..."), the grape varieties
  and the vintage: use it to complete or correct the front label.
- Copy the wine name and producer exactly as written (keep accents); never invent.
- The vintage is the harvest year. Do not confuse it with a founding date ("since 1850")
  or a medal year. If it is not legible, return null.
- Color, region, country and grapes may be inferred from the appellation when the label
  does not state them (e.g. Pauillac -> red, Bordeaux, France, Cabernet Sauvignon/Merlot).
- If the photos do not show wine, set is_wine_label to false and leave the rest empty.
- Write descriptive fields (country, region) in English, e.g. "Burgundy", not "Bourgogne"."""

SUGGEST_SYSTEM = """You are a passionate wine merchant. Given a reference wine and a client's
tastes, suggest real wines, available on the market, that resemble it (style, grapes,
terroir, quality level). Vary the producers and, when relevant, include one or two
alternatives from other regions or countries. Do not include the reference wine or wines
the client has already tasted. Answer in English."""


class VisionError(Exception):
    """User-facing error message."""


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def prepare_image(raw: bytes) -> bytes:
    """Rotate (EXIF), downsize and convert the photo to JPEG."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError) as exc:
        raise VisionError("Unrecognised image format (please use JPEG or PNG).") from exc
    img = img.convert("RGB")
    img.thumbnail((_MAX_SIDE, _MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


def _call_structured(**kwargs: Any):
    try:
        response = _get_client().beta.messages.parse(
            model=settings.claude_model,
            max_tokens=16000,
            betas=[_FALLBACK_BETA],
            fallbacks="default",
            **kwargs,
        )
    except anthropic.AuthenticationError as exc:
        raise VisionError("Invalid or missing Anthropic API key (ANTHROPIC_API_KEY).") from exc
    except anthropic.RateLimitError as exc:
        raise VisionError("Too many requests, please try again in a moment.") from exc
    except anthropic.APIStatusError as exc:
        log.exception("Claude API error (request id %s)", getattr(exc, "request_id", None))
        raise VisionError("The analysis service returned an error.") from exc
    except anthropic.APIConnectionError as exc:
        raise VisionError("Could not reach the analysis service.") from exc

    if response.stop_reason == "refusal":
        raise VisionError("The analysis was declined for this image.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise VisionError("Incomplete analysis, please try again.")
    return response.parsed_output


def read_label(jpegs: list[bytes]) -> LabelInfo:
    """Read a bottle from its photos (front label first, then back label...)."""
    if settings.vision_mock:
        return _mock_label()
    content: list[dict[str, Any]] = []
    for i, jpeg in enumerate(jpegs):
        b64 = base64.standard_b64encode(jpeg).decode()
        content.append({"type": "text", "text": "Front label:" if i == 0 else f"Photo {i + 1} (back label or detail):"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
    content.append({"type": "text", "text": "Read this wine bottle."})
    return _call_structured(
        system=LABEL_SYSTEM,
        output_config={"effort": "medium"},
        output_format=LabelInfo,
        messages=[{"role": "user", "content": content}],
    )


def suggest_similar(reference: dict[str, Any], liked: list[dict[str, Any]], tasted: list[str]) -> SuggestionList:
    if settings.vision_mock:
        return SuggestionList(suggestions=[])
    keep = ("name", "producer", "vintage", "appellation", "region", "country", "color", "grapes")
    payload = {
        "reference_wine": {k: reference.get(k) for k in keep},
        "wines_the_client_liked": [
            {**{k: w.get(k) for k in keep}, "rating": w.get("rating"), "notes": w.get("notes")}
            for w in liked
        ],
        "already_tasted": tasted,
    }
    return _call_structured(
        system=SUGGEST_SYSTEM,
        output_config={"effort": "medium"},
        output_format=SuggestionList,
        messages=[{
            "role": "user",
            "content": "Suggest 5 similar wines.\n\n" + json.dumps(payload, ensure_ascii=False, indent=2),
        }],
    )


def _mock_label() -> LabelInfo:
    return LabelInfo(
        is_wine_label=True,
        name="Château Lynch-Bages",
        producer="Château Lynch-Bages",
        vintage=2016,
        appellation="Pauillac",
        region="Bordeaux",
        country="France",
        color="red",
        grapes=["Cabernet Sauvignon", "Merlot", "Cabernet Franc"],
        classification="5th Growth (Grand Cru Classé)",
        confidence="high",
    )
