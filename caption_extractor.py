from models import ExtractedSource, ExtractionMethod, ErrorCode, SourceType
from platform_detection import detect_platform
from security import SafeFetchError, validate_public_url
from instagram import get_instagram_data
from tiktok import get_tiktok_data
from website import extract_website
from youtube import get_youtube_data


async def extract_source(url: str) -> ExtractedSource:
    platform = detect_platform(url)
    try:
        await validate_public_url(url)
        if platform == "instagram":
            return await get_instagram_data(url)
        if platform == "tiktok":
            return await get_tiktok_data(url)
        if platform == "youtube":
            return await get_youtube_data(url)
        return await extract_website(url)
    except SafeFetchError as exc:
        return ExtractedSource(source_type=SourceType.social if platform != "website" else SourceType.website, platform=platform, extraction_method=ExtractionMethod.social_caption if platform != "website" else ExtractionMethod.website_text, error_code=exc.code, error_message=exc.message)
