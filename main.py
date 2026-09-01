from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import FastAPI, File, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from caption_extractor import extract_source
from config import settings
from qwen import normalize_recipe_image, normalize_recipe_text
from models import ErrorCode, ExtractionMethod, ImportRecipeRequest, ImportResponse, SourceType


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("pinchmeal.imports")
app = FastAPI(title="Pinchmeal Recipe Import API", version="1.0.0", docs_url="/docs" if settings.expose_docs else None)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.monotonic()
    try:
        response = await call_next(request)
    except asyncio.CancelledError:
        logger.info("request_cancelled request_id=%s path=%s", request_id, request.url.path)
        raise
    except Exception:
        logger.exception("unhandled_error request_id=%s path=%s", request_id, request.url.path)
        response = JSONResponse(status_code=500, content={"error_code": ErrorCode.internal_error, "error_message": "The import service could not complete this request."})
    response.headers["x-request-id"] = request_id
    logger.info("request_finished request_id=%s method=%s path=%s status=%s duration_ms=%s", request_id, request.method, request.url.path, response.status_code, int((time.monotonic() - started) * 1000))
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error_code": ErrorCode.invalid_request, "error_message": "The import request is incomplete or invalid."})


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.post("/v1/imports/recipe", response_model=ImportResponse)
async def import_recipe(payload: ImportRecipeRequest, x_pinchmeal_api_token: str | None = Header(default=None)):
    if settings.api_auth_token and x_pinchmeal_api_token != settings.api_auth_token:
        return ImportResponse.failure(payload.source_type, ErrorCode.unauthorized, "This app is not authorized to use the import service.")

    if payload.source_type in {SourceType.ocr_text, SourceType.manual}:
        source_text = (payload.text or "").strip()
        if not source_text:
            return ImportResponse.failure(payload.source_type, ErrorCode.missing_recipe_information, "No readable recipe text was provided.")
        method = ExtractionMethod.ocr_text if payload.source_type == SourceType.ocr_text else ExtractionMethod.manual_entry
        draft, confidence, warnings = await normalize_recipe_text(source_text, method=method)
        if draft is None and "Qwen normalization timed out." in warnings:
            return ImportResponse.failure(payload.source_type, ErrorCode.timeout, "The recipe was read, but structuring it took too long. Please try again.")
        return ImportResponse.from_draft(payload.source_type, ExtractionMethod.ai_normalization if draft else method, draft, field_confidence=confidence, warnings=warnings)

    source = await extract_source(str(payload.url))
    if source.error_code:
        return ImportResponse.failure(payload.source_type, source.error_code, source.error_message or "Unable to read this source.", str(payload.url), source.platform)
    if source.draft is not None:
        return ImportResponse.from_draft(source.source_type, source.extraction_method, source.draft, str(payload.url), source.platform, source.publisher, source.image_url, source.field_confidence, source.warnings)
    if not source.text or len(source.text.strip()) < settings.minimum_source_text_chars:
        return ImportResponse.failure(source.source_type, ErrorCode.missing_recipe_information, "The source did not include enough recipe information to create a draft.", str(payload.url), source.platform)

    draft, confidence, warnings = await normalize_recipe_text(
        source.text,
        method=source.extraction_method,
        thumbnail_url=source.image_url if source.source_type == SourceType.social else None,
        complete_missing=source.source_type == SourceType.social,
    )
    if draft is None:
        if "Qwen normalization timed out." in warnings:
            return ImportResponse.failure(source.source_type, ErrorCode.timeout, "The source was found, but structuring its recipe details took too long. Please try again.", str(payload.url), source.platform)
        return ImportResponse.failure(source.source_type, ErrorCode.normalization_unavailable, "The source was found, but its recipe details could not be structured right now.", str(payload.url), source.platform)
    return ImportResponse.from_draft(source.source_type, ExtractionMethod.ai_normalization, draft, str(payload.url), source.platform, source.publisher, source.image_url, confidence, source.warnings + warnings + [f"Recipe details were normalized from {source.extraction_method.value}; they were not all directly extracted."])


@app.post("/v1/imports/recipe-image", response_model=ImportResponse)
async def import_recipe_image(
    file: UploadFile = File(...),
    x_pinchmeal_api_token: str | None = Header(default=None),
):
    if settings.api_auth_token and x_pinchmeal_api_token != settings.api_auth_token:
        return ImportResponse.failure(SourceType.ocr_text, ErrorCode.unauthorized, "This app is not authorized to use the import service.")
    allowed = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
    if (file.content_type or "").lower() not in allowed:
        return ImportResponse.failure(SourceType.ocr_text, ErrorCode.invalid_request, "Upload a JPEG, PNG, HEIC, HEIF or WebP image.")
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(64 * 1024):
        size += len(chunk)
        if size > settings.maximum_upload_bytes:
            return ImportResponse.failure(SourceType.ocr_text, ErrorCode.response_too_large, "The image is too large to process safely.")
        chunks.append(chunk)
    draft, confidence, warnings = await normalize_recipe_image(b"".join(chunks), file.content_type or "image/jpeg")
    if draft is None and "Qwen normalization timed out." in warnings:
        return ImportResponse.failure(SourceType.ocr_text, ErrorCode.timeout, "The image was read, but structuring its recipe details took too long. Please try again.")
    return ImportResponse.from_draft(SourceType.ocr_text, ExtractionMethod.ai_normalization, draft, field_confidence=confidence, warnings=["The original image was uploaded for this request. Prefer on-device OCR text when possible."] + warnings)


@app.post("/extract-recipe", response_model=ImportResponse, include_in_schema=False)
async def legacy_import(payload: ImportRecipeRequest):
    return await import_recipe(payload)
