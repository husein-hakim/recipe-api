import yt_dlp

def get_youtube_data(url):

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "caption": info.get("description", ""),
        "image": info.get("thumbnail", "")
    }
