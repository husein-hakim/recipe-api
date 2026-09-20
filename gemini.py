from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any
from urllib.parse import quote

import httpx

from config import settings
from models import ExtractionMethod, RecipeDraft
from security import SafeFetchError, safe_fetch


logger = logging.getLogger("pinchmeal.gemini")


_RECIPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "image_url": {"type": ["string", "null"]},
        "source_name": {"type": ["string", "null"]},
        "source_url": {"type": ["string", "null"]},
        "servings": {"type": ["integer", "null"]},
        "prep_time_minutes": {"type": ["integer", "null"]},
        "cook_time_minutes": {"type": ["integer", "null"]},
        "meal_types": {"type": "array", "items": {"type": "string"}},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "amount": {"type": ["number", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]},
                    "optional": {"type": ["boolean", "null"]},
                },
                "required": ["name", "amount", "unit", "notes", "optional"],
                "additionalProperties": False,
            },
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "instruction": {"type": "string"},
                    "timer_minutes": {"type": ["integer", "null"]},
                },
                "required": ["instruction", "timer_minutes"],
                "additionalProperties": False,
            },
        },
        "dietary_tags": {"type": "array", "items": {"type": "string"}},
        "detected_allergens": {"type": "array", "items": {"type": "string"}},
        "calories": {"type": ["integer", "null"], "minimum": 0},
        "protein_grams": {"type": ["number", "null"], "minimum": 0},
        "carbs_grams": {"type": ["number", "null"], "minimum": 0},
        "fat_grams": {"type": ["number", "null"], "minimum": 0},
        "total_cost_minor": {"type": ["integer", "null"], "minimum": 0},
        "cost_per_serving_minor": {"type": ["integer", "null"], "minimum": 0},
        "currency_code": {"type": ["string", "null"]},
    },
    "required": [
        "title", "description", "image_url", "source_name", "source_url", "servings",
        "prep_time_minutes", "cook_time_minutes", "meal_types", "ingredients", "steps",
        "dietary_tags", "detected_allergens", "calories", "protein_grams", "carbs_grams",
        "fat_grams", "total_cost_minor", "cost_per_serving_minor", "currency_code",
    ],
    "additionalProperties": False,
}

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recipe": _RECIPE_SCHEMA,
        "inferred_fields": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["recipe", "inferred_fields"],
    "additionalProperties": False,
}


def _recipe_json_instructions(method: ExtractionMethod, complete_missing: bool = False) -> str:
    completion_rules = """When an important recipe field is missing, use the caption, visible thumbnail, and
ordinary culinary knowledge to infer a sensible value. You may infer a concise title, description, servings,
preparation and cooking times, meal types, ingredient quantities and units, necessary connecting steps, and
step timers. Keep generated values conservative and internally consistent. Do not replace explicit source values
with guesses. The goal is a complete, useful recipe draft.""" if complete_missing else """Do not infer or estimate absent recipe facts. Use null for unknown scalar values and [] for missing lists.
Preserve incomplete source material as an incomplete draft for user review."""

    return f"""Prepare a practical recipe draft as the requested JSON object.

First preserve every explicit fact and the source's wording. {completion_rules}

List every generated or estimated field in inferred_fields using paths such as "title", "servings",
"ingredients[0].amount", or "steps[2]". Do not list fields copied directly from the source.

Always calculate calories, protein_grams, carbs_grams, and fat_grams per serving from the final ingredient
quantities and serving count, even when the source provides no nutrition. Always calculate total_cost_minor
and cost_per_serving_minor using typical mid-range US grocery prices. Costs are integer US cents, currency_code
is USD, and total cost must equal cost per serving multiplied by servings within ordinary rounding tolerance.
These seven fields must be non-null whenever the final recipe has ingredients. Return practical values directly;
do not add estimate labels, approximation symbols, ranges, or explanatory text to the recipe fields.

Never claim that a recipe is allergen-free or medically safe. detected_allergens may identify allergens
present in the final ingredient list, but absence from that list never means verified-free. Do not infer
personal dietary or medical suitability. The client will require explicit allergen review.

The source method is {method.value}. Every inferred value is AI-normalized, not directly extracted."""


def _parse_normalized_content(content: str) -> tuple[RecipeDraft, set[str]]:
    payload: Any = json.loads(content)
    if not isinstance(payload, dict) or not isinstance(payload.get("recipe"), dict):
        raise ValueError("Gemini response was not the expected JSON object")
    raw_inferred = payload.get("inferred_fields") or []
    inferred = {str(field).strip() for field in raw_inferred if str(field).strip()}
    return RecipeDraft.model_validate(payload["recipe"]), inferred


def _confidence(draft: RecipeDraft, inferred: set[str]) -> dict[str, float]:
    def value(field: str, present: bool) -> float:
        if not present:
            return 0.0
        if any(path == field or path.startswith(f"{field}[") or path.startswith(f"{field}.") for path in inferred):
            return 0.45
        return 0.78

    return {
        "title": value("title", bool(draft.title)),
        "description": value("description", bool(draft.description)),
        "servings": value("servings", draft.servings is not None),
        "prep_time_minutes": value("prep_time_minutes", draft.prep_time_minutes is not None),
        "cook_time_minutes": value("cook_time_minutes", draft.cook_time_minutes is not None),
        "meal_types": value("meal_types", bool(draft.meal_types)),
        "ingredients": value("ingredients", bool(draft.ingredients)),
        "steps": value("steps", bool(draft.steps)),
        "calories": value("calories", draft.calories is not None),
        "protein_grams": value("protein_grams", draft.protein_grams is not None),
        "carbs_grams": value("carbs_grams", draft.carbs_grams is not None),
        "fat_grams": value("fat_grams", draft.fat_grams is not None),
        "total_cost_minor": value("total_cost_minor", draft.total_cost_minor is not None),
        "cost_per_serving_minor": value("cost_per_serving_minor", draft.cost_per_serving_minor is not None),
    }


def _inference_warnings(inferred: set[str], used_thumbnail: bool) -> list[str]:
    warnings: list[str] = []
    if inferred:
        warnings.append("Gemini completed missing recipe details. Review quantities, timings, servings, and generated steps before saving.")
    if used_thumbnail:
        warnings.append("The public social thumbnail was sent to Gemini together with the caption to help prepare this draft.")
    return warnings


async def _thumbnail_part(url: str | None) -> dict[str, Any] | None:
    if not url:
        return None
    try:
        _, image, content_type = await safe_fetch(url)
    except SafeFetchError as exc:
        logger.info("social_thumbnail_unavailable reason=%s", exc.code.value)
        return None
    mime_type = content_type.split(";", 1)[0].strip().lower()
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        logger.info("social_thumbnail_unsupported_mime mime=%s", mime_type or "missing")
        return None
    return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(image).decode("ascii")}}


async def _generate(model: str, system_instruction: str, parts: list[dict[str, Any]]) -> str | None:
    endpoint = f"{settings.gemini_base_url.rstrip('/')}/models/{quote(model, safe='')}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 5_000,
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseJsonSchema": _RESPONSE_SCHEMA,
        },
    }
    timeout = httpx.Timeout(settings.gemini_timeout_seconds, connect=min(10.0, settings.gemini_timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            endpoint,
            headers={"x-goog-api-key": settings.gemini_api_key or "", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        return None
    response_parts = ((candidates[0].get("content") or {}).get("parts") or [])
    return "".join(str(part.get("text") or "") for part in response_parts).strip() or None


async def normalize_recipe_text(
    source_text: str,
    method: ExtractionMethod,
    thumbnail_url: str | None = None,
    complete_missing: bool = False,
) -> tuple[RecipeDraft | None, dict[str, float], list[str]]:
    if not settings.gemini_api_key:
        return None, {}, ["Gemini normalization is not configured on this server."]

    thumbnail = await _thumbnail_part(thumbnail_url)
    parts: list[dict[str, Any]] = [{"text": f"Complete this recipe source as the required JSON object:\n\n{source_text[:100_000]}"}]
    if thumbnail:
        parts.append(thumbnail)

    try:
        content = await _generate(
            settings.gemini_vision_model if thumbnail else settings.gemini_text_model,
            _recipe_json_instructions(method, complete_missing=complete_missing),
            parts,
        )
        if not content:
            return None, {}, ["Gemini returned no recipe JSON."]
        draft, inferred = _parse_normalized_content(content)
        return draft, _confidence(draft, inferred), _inference_warnings(inferred, thumbnail is not None)
    except asyncio.CancelledError:
        raise
    except httpx.TimeoutException:
        logger.warning("gemini_text_normalization_timed_out method=%s", method.value)
        return None, {}, ["Gemini normalization timed out."]
    except Exception:
        logger.exception("gemini_text_normalization_failed method=%s", method.value)
        return None, {}, ["Gemini recipe normalization is temporarily unavailable."]


async def normalize_recipe_image(
    image: bytes,
    mime_type: str,
) -> tuple[RecipeDraft | None, dict[str, float], list[str]]:
    if not settings.gemini_api_key:
        return None, {}, ["Gemini vision normalization is not configured on this server."]

    parts = [
        {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(image).decode("ascii")}},
        {"text": "Transcribe and structure only recipe information visibly present in this image. Use null for anything unreadable or absent."},
    ]
    try:
        content = await _generate(
            settings.gemini_vision_model,
            _recipe_json_instructions(ExtractionMethod.ocr_text, complete_missing=False),
            parts,
        )
        if not content:
            return None, {}, ["Gemini Vision returned no recipe JSON."]
        draft, inferred = _parse_normalized_content(content)
        return draft, _confidence(draft, inferred), _inference_warnings(inferred, False) + ["Image-derived fields require review before saving."]
    except asyncio.CancelledError:
        raise
    except httpx.TimeoutException:
        logger.warning("gemini_image_normalization_timed_out")
        return None, {}, ["Gemini normalization timed out."]
    except Exception:
        logger.exception("gemini_image_normalization_failed")
        return None, {}, ["Gemini image normalization is temporarily unavailable."]
