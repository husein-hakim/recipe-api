from platform_detection import detect_platform
from instagram import get_instagram_data
from youtube import get_youtube_data
from tiktok import get_tiktok_data
from website import extract_structured_recipe, get_webpage_text, extract_image_from_website

def caption_extractor(url):
    platform = detect_platform(url)

    if platform == 'instagram':
        return get_instagram_data(url)

    elif platform == 'youtube':
        return get_youtube_data(url)

    elif platform == 'tiktok':
        return get_tiktok_data(url)

    else:
        structured = extract_structured_recipe(url)
        image = extract_image_from_website(url)

        if structured:
            return {
                "type": "structured",
                "data": structured,
                "image": (
                    structured.get("image")[0]
                    if isinstance(structured.get("image"), list)
                    else structured.get("image")
                ) or image
            }

        text = get_webpage_text(url)

        return {
            "type": "text",
            "caption": text,
            "image": image
        }