from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from gemini import generate_recipe_from_image

from caption_extractor import caption_extractor
from gemini import generate_recipe

app = FastAPI()


class RecipeRequest(BaseModel):
    url: str


@app.post("/extract-recipe")
def extract_recipe(req: RecipeRequest):

    data = caption_extractor(req.url)

    if not data:
        raise HTTPException(status_code=400, detail="Could not extract data")

    # 🟢 CASE 1: Structured recipe (no AI needed)
    if data.get("type") == "structured":
        return {
            "source": "website",
            "recipe": data["data"],
            "image": data.get("image")
        }

    # 🟢 CASE 2: Social / text → use Gemini
    caption = data.get("caption")

    if not caption:
        raise HTTPException(status_code=400, detail="No caption found")

    recipe = generate_recipe(caption)

    return {
        "source": "ai",
        "recipe": recipe,
        "image": data.get("image")
    }

@app.post("/extract-recipe-from-image")
async def extract_recipe_from_image(file: UploadFile = File(...)):

    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    contents = await file.read()

    try:
        recipe = generate_recipe_from_image(contents)
        return {
            "source": "image",
            "recipe": recipe
        }

    except Exception as e:
        print("Image processing error:", e)
        raise HTTPException(status_code=500, detail="Failed to process image")
