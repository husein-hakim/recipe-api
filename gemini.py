from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional
import os

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class Ingredient(BaseModel):
    name: str = Field(
        description="Name of the ingredient only. Use the simplest common name. "
                    "Strip all context like 'for the sauce', 'for garnish', 'for the dough' etc. "
                    "Examples: 'sugar' not 'sugar (for sauce)', 'butter' not 'butter (softened, for filling)', "
                    "'flour' not 'all-purpose flour (for dusting)'. Just the core ingredient name."
    )
    quantity: str = Field(
        description="Quantity of the ingredient including units, e.g. '2 cups', '400g', '1 tbsp'. "
                    "Do not include the ingredient name here."
    )

class Recipe(BaseModel):
    recipe_name: str = Field(description="The name of the recipe.")
    prep_time_minutes: Optional[int] = Field(description="Optional time in minutes to prepare the recipe.")
    total_time_minutes: int = Field(description='Total time in minutes including prep time and time to finish the entire recipe.')
    servings: int = Field(description='servings of the dish which will be prepared with the given quantities')
    protein: int = Field(description='Protein in 1 serving of the recipe')
    carbs: int = Field(description='Carbohydrates in 1 serving of the recipe')
    fats: int = Field(description='Fats in 1 serving of the recipe')
    ingredients: List[Ingredient]
    instructions: List[str]

def generate_recipe(caption):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    prompt = f"""
    Fill missing details logically.
    IMPORTANT: Ingredient names must be simple and clean — no parenthetical notes,
    no preparation context, no part-of-dish qualifiers.

    Caption:
    {caption}
    """

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": Recipe.model_json_schema(),
        },
    )

    return Recipe.model_validate_json(response.text)

def generate_recipe_from_image(image_bytes):

    prompt = """
        Extract a complete recipe from this image.
        The image may contain handwritten notes, printed recipes, or screenshots.
        Return a complete structured recipe. Fill missing details logically if needed.
        IMPORTANT: Ingredient names must be simple and clean — no parenthetical notes,
        no preparation context (e.g. 'softened', 'chopped'), no part-of-dish qualifiers
        (e.g. 'for the sauce', 'for garnish'). Just the core ingredient name.
    """

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_bytes
                        }
                    }
                ]
            }
        ],
        config={
            "response_mime_type": "application/json",
            "response_json_schema": Recipe.model_json_schema(),
        },
    )

    return Recipe.model_validate_json(response.text)