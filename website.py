import requests
from bs4 import BeautifulSoup
import json


def get_soup(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    return BeautifulSoup(response.text, "html.parser")


def extract_structured_recipe(url):
    soup = get_soup(url)

    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        if not script.string:
            continue

        try:
            data = json.loads(script.string)

            # 🔥 Handle list
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Recipe":
                        return item

            # Single object
            if isinstance(data, dict) and data.get("@type") == "Recipe":
                return data

        except:
            continue

    return None


def get_webpage_text(url):
    soup = get_soup(url)
    return soup.get_text()

def extract_image_from_website(url):
    soup = get_soup(url)

    # ✅ 1. Try Open Graph (BEST fallback)
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"]

    # ✅ 2. Fallback to first image
    img = soup.find("img")
    if img and img.get("src"):
        return img["src"]

    return None