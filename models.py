from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator


class SourceType(str, Enum):
    website = "website"
    social = "social"
    ocr_text = "ocrText"
    manual = "manual"


class ExtractionMethod(str, Enum):
    website_json_ld = "websiteJSONLD"
    website_text = "websiteText"
    social_caption = "socialCaption"
    ocr_text = "ocrText"
    manual_entry = "manualEntry"
    ai_normalization = "aiNormalization"


class ImportStatus(str, Enum):
    complete = "complete"
    incomplete = "incomplete"
    failed = "failed"


class ErrorCode(str, Enum):
    invalid_request = "invalid_request"
    unauthorized = "unauthorized"
    unsupported_url = "unsupported_url"
    unsafe_url = "unsafe_url"
    source_unavailable = "source_unavailable"
    private_source = "private_source"
    deleted_source = "deleted_source"
    unsupported_source = "unsupported_source"
    response_too_large = "response_too_large"
    timeout = "timeout"
    missing_recipe_information = "missing_recipe_information"
    normalization_unavailable = "normalization_unavailable"
    internal_error = "internal_error"


class IngredientDraft(BaseModel):
    name: str
    amount: float | None = None
    unit: str | None = None
    notes: str | None = None
    optional: bool | None = None


class StepDraft(BaseModel):
    instruction: str
    timer_minutes: int | None = None


class RecipeDraft(BaseModel):
    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    servings: int | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    meal_types: list[str] = Field(default_factory=list)
    ingredients: list[IngredientDraft] = Field(default_factory=list)
    steps: list[StepDraft] = Field(default_factory=list)
    dietary_tags: list[str] = Field(default_factory=list)
    detected_allergens: list[str] = Field(default_factory=list)
    calories: int | None = Field(default=None, ge=0)
    protein_grams: float | None = Field(default=None, ge=0)
    carbs_grams: float | None = Field(default=None, ge=0)
    fat_grams: float | None = Field(default=None, ge=0)
    total_cost_minor: int | None = Field(default=None, ge=0)
    cost_per_serving_minor: int | None = Field(default=None, ge=0)
    currency_code: str | None = None
    content_fingerprint: str | None = None

    @model_validator(mode="after")
    def clean(self):
        self.title = clean_optional(self.title)
        self.description = clean_optional(self.description)
        self.source_name = clean_optional(self.source_name)
        self.currency_code = clean_optional(self.currency_code)
        self.ingredients = [item for item in self.ingredients if clean_optional(item.name)]
        self.steps = [item for item in self.steps if clean_optional(item.instruction)]
        canonical = "|".join([(self.title or "").lower(), *[i.name.lower() for i in self.ingredients], *[s.instruction.lower() for s in self.steps]])
        self.content_fingerprint = hashlib.sha256(canonical.encode()).hexdigest() if canonical.strip("|") else None
        return self

    def missing_required_fields(self) -> list[str]:
        return (["title"] if not self.title else []) + (["ingredients"] if not self.ingredients else []) + (["steps"] if not self.steps else [])


class ImportRecipeRequest(BaseModel):
    source_type: SourceType = SourceType.website
    url: HttpUrl | None = None
    text: str | None = Field(default=None, max_length=100_000)

    @model_validator(mode="after")
    def source_present(self):
        if self.source_type in {SourceType.website, SourceType.social} and self.url is None:
            raise ValueError("url is required")
        if self.source_type in {SourceType.ocr_text, SourceType.manual} and not (self.text or "").strip():
            raise ValueError("text is required")
        return self


class ImportResponse(BaseModel):
    api_version: str = "v1"
    import_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ImportStatus
    source_type: SourceType
    original_source_url: str | None = None
    source_platform: str | None = None
    publisher_or_creator: str | None = None
    source_image_url: str | None = None
    extraction_method: ExtractionMethod | None = None
    recipe_draft: RecipeDraft | None = None
    field_confidence: dict[str, float] = Field(default_factory=dict)
    missing_required_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: ErrorCode | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def failure(cls, source_type: SourceType, code: ErrorCode, message: str, original_source_url: str | None = None, platform: str | None = None):
        return cls(status=ImportStatus.failed, source_type=source_type, original_source_url=original_source_url, source_platform=platform, error_code=code, error_message=message)

    @classmethod
    def from_draft(cls, source_type: SourceType, extraction_method: ExtractionMethod, draft: RecipeDraft | None, original_source_url: str | None = None, platform: str | None = None, publisher: str | None = None, source_image_url: str | None = None, field_confidence: dict[str, float] | None = None, warnings: list[str] | None = None):
        if draft is None:
            return cls.failure(source_type, ErrorCode.missing_recipe_information, "No recipe draft could be created.", original_source_url, platform)
        draft.source_url = draft.source_url or original_source_url
        draft.source_name = draft.source_name or publisher
        draft.image_url = draft.image_url or source_image_url
        missing = draft.missing_required_fields()
        return cls(status=ImportStatus.incomplete if missing else ImportStatus.complete, source_type=source_type, original_source_url=original_source_url, source_platform=platform, publisher_or_creator=publisher, source_image_url=source_image_url, extraction_method=extraction_method, recipe_draft=draft, field_confidence=field_confidence or {}, missing_required_fields=missing, warnings=(warnings or []) + (["Review and complete the highlighted fields before planning this recipe."] if missing else []))


class ExtractedSource(BaseModel):
    source_type: SourceType
    platform: str
    extraction_method: ExtractionMethod
    text: str | None = None
    draft: RecipeDraft | None = None
    publisher: str | None = None
    image_url: str | None = None
    field_confidence: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error_code: ErrorCode | None = None
    error_message: str | None = None


def clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None
