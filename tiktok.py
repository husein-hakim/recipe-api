import json
import logging
from urllib.parse import urlencode

from models import ExtractedSource, ExtractionMethod, ErrorCode, SourceType
from security import SafeFetchError, safe_fetch
from ytdlp_metadata import YTDLPMetadataError, extract_ytdlp_metadata


logger = logging.getLogger("pinchmeal.imports.tiktok")


async def _official_oembed(url: str) -> ExtractedSource | None:
    endpoint = "https://www.tiktok.com/oembed?" + urlencode({"url": url})
    try:
        _, content, content_type = await safe_fetch(endpoint)
        if "json" not in content_type.lower():
            return None
        payload = json.loads(content)
        caption = str(payload.get("title") or "").strip()
        if not caption:
            return None
        author = str(payload.get("author_name") or "").strip()
        thumbnail = str(payload.get("thumbnail_url") or "").strip()
        return ExtractedSource(
            source_type=SourceType.social,
            platform="tiktok",
            extraction_method=ExtractionMethod.social_caption,
            text=caption,
            publisher=f"TikTok {author}" if author else "TikTok",
            image_url=thumbnail or None,
            warnings=["TikTok's public embed metadata was used; video-only instructions are not invented."],
        )
    except (SafeFetchError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.info("tiktok_oembed_unavailable error_type=%s", type(exc).__name__)
        return None


async def get_tiktok_data(url: str) -> ExtractedSource:
    official = await _official_oembed(url)
    if official is not None:
        return official

    try:
        metadata = await extract_ytdlp_metadata(url)
        caption = metadata.description
        if not caption:
            return ExtractedSource(source_type=SourceType.social, platform="tiktok", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.missing_recipe_information, error_message="This TikTok post does not include enough recipe text.")
        return ExtractedSource(source_type=SourceType.social, platform="tiktok", extraction_method=ExtractionMethod.social_caption, text=caption, publisher=metadata.publisher or "TikTok", image_url=metadata.thumbnail_url, warnings=["Social captions can omit quantities or instructions; review all fields."])
    except YTDLPMetadataError as exc:
        logger.warning("tiktok_metadata_failed reason=%s", exc.reason)
        if exc.reason == "authentication_required":
            return ExtractedSource(source_type=SourceType.social, platform="tiktok", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.private_source, error_message="TikTok required sign-in or blocked automated access to this post.")
        if exc.reason == "unsupported":
            return ExtractedSource(source_type=SourceType.social, platform="tiktok", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.unsupported_source, error_message="This kind of TikTok link is not supported.")
        if exc.reason == "unavailable":
            return ExtractedSource(source_type=SourceType.social, platform="tiktok", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.deleted_source, error_message="This TikTok post is unavailable or was deleted.")
        return ExtractedSource(source_type=SourceType.social, platform="tiktok", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.source_unavailable, error_message="TikTok could not be read right now. Try again later or paste the recipe text manually.")
