from urllib.parse import urlsplit


def detect_platform(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host == "instagram.com" or host.endswith(".instagram.com"):
        return "instagram"
    if host in {"youtu.be", "youtube.com"} or host.endswith(".youtube.com"):
        return "youtube"
    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        return "tiktok"
    return "website"
