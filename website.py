from __future__ import annotations

import json
import re
from datetime import timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import ExtractedSource, ExtractionMethod, IngredientDraft, RecipeDraft, SourceType, StepDraft
from security import safe_fetch


def _find_recipe(value):
    if isinstance(value, dict):
        kind = value.get("@type")
        if kind == "Recipe" or (isinstance(kind, list) and "Recipe" in kind):
            return value
        for nested in value.values():
            found = _find_recipe(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_recipe(item)
            if found:
                return found
    return None


def _minutes(value) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?", str(value), re.I)
    if not match:
        return None
    return int(match.group(1) or 0) * 60 + int(match.group(2) or 0)


def _yield(value) -> int | None:
    if isinstance(value, list):
        value = value[0] if value else None
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def _image(value, base_url: str) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    return urljoin(base_url, value) if value else None


def _publisher(data) -> str | None:
    value = data.get("author") or data.get("publisher")
    if isinstance(value, list):
        value = value[0] if value else None
    return value.get("name") if isinstance(value, dict) else (str(value) if value else None)


def _steps(value) -> list[StepDraft]:
    result: list[StepDraft] = []
    def append(item):
        if isinstance(item, str) and item.strip():
            result.append(StepDraft(instruction=item.strip()))
        elif isinstance(item, dict):
            if item.get("@type") == "HowToSection":
                for child in item.get("itemListElement") or []:
                    append(child)
            elif item.get("text") or item.get("name"):
                result.append(StepDraft(instruction=(item.get("text") or item.get("name")).strip()))
    for item in value if isinstance(value, list) else [value]:
        append(item)
    return result


def _draft_from_json_ld(data: dict, source_url: str) -> RecipeDraft:
    publisher = _publisher(data)
    return RecipeDraft(
        title=data.get("name"),
        description=BeautifulSoup(str(data.get("description") or ""), "html.parser").get_text(" ", strip=True) or None,
        image_url=_image(data.get("image"), source_url),
        source_name=publisher,
        source_url=source_url,
        servings=_yield(data.get("recipeYield")),
        prep_time_minutes=_minutes(data.get("prepTime")),
        cook_time_minutes=_minutes(data.get("cookTime")),
        meal_types=[str(data.get("recipeCategory"))] if data.get("recipeCategory") else [],
        ingredients=[IngredientDraft(name=str(item).strip()) for item in data.get("recipeIngredient") or [] if str(item).strip()],
        steps=_steps(data.get("recipeInstructions") or []),
        dietary_tags=[str(item) for item in (data.get("suitableForDiet") if isinstance(data.get("suitableForDiet"), list) else [data.get("suitableForDiet")]) if item],
    )


async def extract_website(url: str) -> ExtractedSource:
    final_url, body, content_type = await safe_fetch(url)
    if "html" not in content_type.lower() and content_type:
        return ExtractedSource(source_type=SourceType.website, platform="website", extraction_method=ExtractionMethod.website_text, error_code="unsupported_source", error_message="This link is not a supported recipe page.")
    soup = BeautifulSoup(body, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            found = _find_recipe(json.loads(script.string or ""))
            if found:
                draft = _draft_from_json_ld(found, final_url)
                return ExtractedSource(source_type=SourceType.website, platform="website", extraction_method=ExtractionMethod.website_json_ld, draft=draft, publisher=draft.source_name, image_url=draft.image_url, field_confidence={"title": .98, "ingredients": .98, "steps": .96, "servings": .9, "prep_time_minutes": .9, "cook_time_minutes": .9})
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    image_tag = soup.find("meta", property="og:image")
    publisher = soup.find("meta", property="og:site_name")
    for node in soup(["script", "style", "nav", "footer", "noscript"]):
        node.decompose()
    text = soup.get_text("\n", strip=True)[:100_000]
    return ExtractedSource(source_type=SourceType.website, platform="website", extraction_method=ExtractionMethod.website_text, text=text, publisher=publisher.get("content") if publisher else None, image_url=urljoin(final_url, image_tag.get("content")) if image_tag and image_tag.get("content") else None, warnings=["No structured recipe data was available; review the text-derived draft carefully."])
