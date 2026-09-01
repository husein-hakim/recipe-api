import asyncio
import logging
from urllib.parse import unquote, urlsplit

from models import ExtractedSource, ExtractionMethod, ErrorCode, SourceType
from ytdlp_metadata import YTDLPMetadataError, extract_ytdlp_metadata


logger = logging.getLogger("pinchmeal.imports.instagram")


def _shortcode(url: str) -> str | None:
    parts = [unquote(part) for part in urlsplit(url).path.split("/") if part]
    if len(parts) >= 2 and parts[0].lower() in {"p", "reel", "tv"}:
        return parts[1]
    return None


async def _instaloader_metadata(url: str) -> tuple[str, str | None, str | None]:
    shortcode = _shortcode(url)
    if not shortcode:
        raise ValueError("unsupported_instagram_url")

    import instaloader

    def load():
        loader = instaloader.Instaloader(download_pictures=False, download_videos=False, save_metadata=False, quiet=True)
        return instaloader.Post.from_shortcode(loader.context, shortcode)

    post = await asyncio.to_thread(load)
    caption = (post.caption or "").strip()
    publisher = f"Instagram @{post.owner_username}" if post.owner_username else "Instagram"
    return caption, publisher, post.url


async def get_instagram_data(url: str) -> ExtractedSource:
    try:
        caption, publisher, image_url = await _instaloader_metadata(url)
        if not caption:
            return ExtractedSource(source_type=SourceType.social, platform="instagram", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.missing_recipe_information, error_message="This Instagram post does not include enough recipe text.")
        return ExtractedSource(source_type=SourceType.social, platform="instagram", extraction_method=ExtractionMethod.social_caption, text=caption, publisher=publisher, image_url=image_url, warnings=["Social imports are best-effort and may be incomplete."])
    except Exception as exc:
        logger.warning("instagram_instaloader_failed error_type=%s", type(exc).__name__)

    try:
        metadata = await extract_ytdlp_metadata(url)
        if not metadata.description:
            return ExtractedSource(source_type=SourceType.social, platform="instagram", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.missing_recipe_information, error_message="This Instagram post does not include enough recipe text.")
        return ExtractedSource(source_type=SourceType.social, platform="instagram", extraction_method=ExtractionMethod.social_caption, text=metadata.description, publisher=metadata.publisher or "Instagram", image_url=metadata.thumbnail_url, warnings=["Instagram was read using a fallback extractor; review all imported fields."])
    except YTDLPMetadataError as exc:
        logger.warning("instagram_fallback_failed reason=%s", exc.reason)
        if exc.reason == "authentication_required":
            return ExtractedSource(source_type=SourceType.social, platform="instagram", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.private_source, error_message="Instagram required sign-in or blocked automated access to this post.")
        if exc.reason == "unsupported":
            return ExtractedSource(source_type=SourceType.social, platform="instagram", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.unsupported_source, error_message="Use a direct Instagram post, reel, or TV URL.")
        if exc.reason == "unavailable":
            return ExtractedSource(source_type=SourceType.social, platform="instagram", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.deleted_source, error_message="This Instagram post is unavailable or was deleted.")
        return ExtractedSource(source_type=SourceType.social, platform="instagram", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.source_unavailable, error_message="Instagram could not be read right now. Try again later or paste the recipe caption manually.")
