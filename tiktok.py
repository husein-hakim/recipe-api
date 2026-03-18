from TikTokApi import TikTokApi

def get_tiktok_data(url):

    with TikTokApi() as api:
        video = api.video(url=url)
        info = video.info()

    return {
        "caption": info["desc"],
        "image": info["video"]["cover"]
    }