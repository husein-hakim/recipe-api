from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlsplit

import httpx

from config import settings
from models import RecipeImageCandidate


logger = logging.getLogger("pinchmeal.images")


def _source_name(url: str) -> str:
    host = (urlsplit(url).hostname or "Image source").lower()
    return host.removeprefix("www.")


def _integer(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _candidate(raw: object) -> RecipeImageCandidate | None:
    if isinstance(raw, str):
        image_url = raw.strip()
        width = height = None
        source_url = image_url
    elif isinstance(raw, dict):
        image_url = str(raw.get("url") or raw.get("original") or "").strip()
        width = _integer(raw.get("width") or raw.get("original_width"))
        height = _integer(raw.get("height") or raw.get("original_height"))
        source_url = str(raw.get("source_url") or raw.get("link") or image_url).strip()
    else:
        return None

    parsed = urlsplit(image_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None

    return RecipeImageCandidate(
        image_url=image_url,
        source_url=source_url if urlsplit(source_url).scheme in {"http", "https"} else image_url,
        source_name=_source_name(source_url or image_url),
        width=width,
        height=height,
    )


async def search_recipe_images(title: str) -> list[RecipeImageCandidate]:
    if not settings.cognify_api_key:
        raise RuntimeError("not_configured")

    # Qwen's concise dish title is intentionally the entire query. Extra camera,
    # styling, cuisine, and meal-category terms made Google results less relevant.
    query = re.sub(r"\s+", " ", title).strip()[:160]
    timeout = httpx.Timeout(settings.cognify_timeout_seconds, connect=min(6.0, settings.cognify_timeout_seconds))
    headers = {
        "x-rapidapi-host": settings.cognify_api_host,
        "x-rapidapi-key": settings.cognify_api_key,
        "User-Agent": settings.user_agent,
    }
    params = {
        "query": query,
        "count": min(30, max(3, settings.cognify_candidate_count)),
        "imageInfo": "true",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(f"{settings.cognify_base_url.rstrip('/')}/getGoogleImages", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except asyncio.CancelledError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("cognify_request_failed error_type=%s", type(exc).__name__)
        raise RuntimeError("provider_unavailable") from exc

    raw_images = payload.get("images", []) if isinstance(payload, dict) else []
    candidates: list[RecipeImageCandidate] = []
    seen: set[str] = set()
    for raw in raw_images:
        item = _candidate(raw)
        if item is None or item.image_url in seen:
            continue
        seen.add(item.image_url)
        candidates.append(item)

    # Preserve the provider's ranking. The app intentionally uses the first result.
    return candidates[:8]
