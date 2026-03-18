def detect_platform(url):
    if 'instagram.com' in url:
        return 'instagram'

    if 'youtube.com' in url:
        return 'youtube'

    if 'tiktok.com' in url:
        return 'tiktok'