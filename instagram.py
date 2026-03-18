import instaloader

L = instaloader.Instaloader()

def get_instagram_data(url):

    shortcode = url.split("/")[-2]
    post = instaloader.Post.from_shortcode(L.context, shortcode)

    return {
        "caption": post.caption,
        "image": post.url  # thumbnail image
    }