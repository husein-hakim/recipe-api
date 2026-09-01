import logging

from models import ExtractedSource, ExtractionMethod, ErrorCode, SourceType
from ytdlp_metadata import YTDLPMetadataError, extract_ytdlp_metadata


logger = logging.getLogger("pinchmeal.imports.youtube")


async def get_youtube_data(url: str) -> ExtractedSource:
    try:
        metadata = await extract_ytdlp_metadata(url)
        description = metadata.description
        if not description:
            return ExtractedSource(source_type=SourceType.social, platform="youtube", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.missing_recipe_information, error_message="This video does not include enough recipe information in its description.")
        return ExtractedSource(source_type=SourceType.social, platform="youtube", extraction_method=ExtractionMethod.social_caption, text=description, publisher=metadata.publisher or "YouTube", image_url=metadata.thumbnail_url, warnings=["Only the creator-provided description was used; video-only instructions are not invented."])
    except YTDLPMetadataError as exc:
        logger.warning("youtube_metadata_failed reason=%s", exc.reason)
        if exc.reason == "authentication_required":
            return ExtractedSource(source_type=SourceType.social, platform="youtube", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.private_source, error_message="YouTube required sign-in or blocked automated access to this video.")
        if exc.reason == "unsupported":
            return ExtractedSource(source_type=SourceType.social, platform="youtube", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.unsupported_source, error_message="This kind of YouTube link is not supported.")
        if exc.reason == "unavailable":
            return ExtractedSource(source_type=SourceType.social, platform="youtube", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.deleted_source, error_message="This YouTube video is unavailable or was deleted.")
        return ExtractedSource(source_type=SourceType.social, platform="youtube", extraction_method=ExtractionMethod.social_caption, error_code=ErrorCode.source_unavailable, error_message="YouTube could not be read right now. Try again later or paste the recipe text manually.")
