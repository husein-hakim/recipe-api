from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from openai import APITimeoutError, OpenAI

from config import settings
from models import ExtractionMethod, RecipeDraft
from security import SafeFetchError, safe_fetch


logger = logging.getLogger("pinchmeal.qwen")


def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.qwen_api_key,
        base_url=settings.qwen_base_url,
        timeout=settings.qwen_timeout_seconds,
        max_retries=0,
    )


def _recipe_json_instructions(method: ExtractionMethod, complete_missing: bool = False) -> str:
    completion_rules = """When an important recipe field is missing, use the caption, visible thumbnail, and
ordinary culinary knowledge to infer a sensible value. You may infer a concise title, description, servings,
preparation and cooking times, meal types, ingredient quantities and units, necessary connecting steps, and
step timers. Keep generated values conservative and internally consistent. Do not replace explicit source values
with guesses. The goal is a complete, useful recipe draft.""" if complete_missing else """Do not infer or estimate absent recipe facts. Use null for unknown scalar values and [] for missing lists.
Preserve incomplete source material as an incomplete draft for user review."""

    return f"""Return one valid JSON object containing a practical recipe draft.

First preserve every explicit fact and the source's wording. {completion_rules}

Return exactly this top-level structure:
{{
  "recipe": {{
    "title": string|null,
    "description": string|null,
    "image_url": null,
    "source_name": null,
    "source_url": null,
    "servings": integer|null,
    "prep_time_minutes": integer|null,
    "cook_time_minutes": integer|null,
    "meal_types": [string],
    "ingredients": [{{"name": string, "amount": number|null, "unit": string|null, "notes": string|null, "optional": boolean|null}}],
    "steps": [{{"instruction": string, "timer_minutes": integer|null}}],
    "dietary_tags": [string],
    "detected_allergens": [string],
    "calories": integer,
    "protein_grams": number,
    "carbs_grams": number,
    "fat_grams": number,
    "total_cost_minor": integer,
    "cost_per_serving_minor": integer,
    "currency_code": "USD"
  }},
  "inferred_fields": [string]
}}

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
    if not isinstance(payload, dict):
        raise ValueError("Qwen response was not a JSON object")
    if isinstance(payload.get("recipe"), dict):
        recipe_payload = payload["recipe"]
        raw_inferred = payload.get("inferred_fields") or []
    else:
        recipe_payload = payload
        raw_inferred = []
    inferred = {str(field).strip() for field in raw_inferred if str(field).strip()}
    return RecipeDraft.model_validate(recipe_payload), inferred


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
        warnings.append("Qwen completed missing recipe details. Review quantities, timings, servings, and generated steps before saving.")
    if used_thumbnail:
        warnings.append("The public social thumbnail was sent to Qwen together with the caption to help prepare this draft.")
    return warnings


async def _thumbnail_data_url(url: str | None) -> str | None:
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
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def normalize_recipe_text(
    source_text: str,
    method: ExtractionMethod,
    thumbnail_url: str | None = None,
    complete_missing: bool = False,
) -> tuple[RecipeDraft | None, dict[str, float], list[str]]:
    if not settings.qwen_api_key:
        return None, {}, ["Qwen normalization is not configured on this server."]

    thumbnail_data_url = await _thumbnail_data_url(thumbnail_url)

    def request() -> str | None:
        user_content: str | list[dict[str, Any]]
        prompt = f"Complete this recipe source as the required JSON object:\n\n{source_text[:100_000]}"
        if thumbnail_data_url:
            user_content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": thumbnail_data_url}},
            ]
        else:
            user_content = prompt
        completion = _client().chat.completions.create(
            model=settings.qwen_vision_model if thumbnail_data_url else settings.qwen_text_model,
            messages=[
                {"role": "system", "content": _recipe_json_instructions(method, complete_missing=complete_missing)},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
            temperature=0,
            max_tokens=5_000,
        )
        return completion.choices[0].message.content

    try:
        content = await asyncio.to_thread(request)
        if not content:
            return None, {}, ["Qwen returned no recipe JSON."]
        draft, inferred = _parse_normalized_content(content)
        return draft, _confidence(draft, inferred), _inference_warnings(inferred, thumbnail_data_url is not None)
    except asyncio.CancelledError:
        raise
    except APITimeoutError:
        logger.warning("qwen_text_normalization_timed_out method=%s", method.value)
        return None, {}, ["Qwen normalization timed out."]
    except Exception:
        logger.exception("qwen_text_normalization_failed method=%s", method.value)
        return None, {}, ["Qwen recipe normalization is temporarily unavailable."]


async def normalize_recipe_image(
    image: bytes,
    mime_type: str,
) -> tuple[RecipeDraft | None, dict[str, float], list[str]]:
    if not settings.qwen_api_key:
        return None, {}, ["Qwen vision normalization is not configured on this server."]

    encoded = base64.b64encode(image).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"

    def request() -> str | None:
        completion = _client().chat.completions.create(
            model=settings.qwen_vision_model,
            messages=[
                {
                    "role": "system",
                    "content": _recipe_json_instructions(ExtractionMethod.ocr_text, complete_missing=False),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {
                            "type": "text",
                            "text": "Transcribe and structure only recipe information visibly present in this image as JSON. Use null for anything unreadable or absent.",
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
            temperature=0,
            max_tokens=5_000,
        )
        return completion.choices[0].message.content

    try:
        content = await asyncio.to_thread(request)
        if not content:
            return None, {}, ["Qwen Vision returned no recipe JSON."]
        draft, inferred = _parse_normalized_content(content)
        return draft, _confidence(draft, inferred), _inference_warnings(inferred, False) + ["Image-derived fields require review before saving."]
    except asyncio.CancelledError:
        raise
    except APITimeoutError:
        logger.warning("qwen_image_normalization_timed_out")
        return None, {}, ["Qwen normalization timed out."]
    except Exception:
        logger.exception("qwen_image_normalization_failed")
        return None, {}, ["Qwen image normalization is temporarily unavailable."]
