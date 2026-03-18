from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class Ingredient(BaseModel):
    name: str = Field(description="Name of the ingredient.")
    quantity: str = Field(description="Quantity of the ingredient, including units.")

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
    Extract a complete recipe from this caption.
    Fill missing details logically.

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