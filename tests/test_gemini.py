import json
import unittest
from unittest.mock import AsyncMock, patch

import gemini
from models import ExtractionMethod


def recipe_response(inferred_fields=None):
    return json.dumps(
        {
            "recipe": {
                "title": "Tomato Toast",
                "description": None,
                "image_url": None,
                "source_name": None,
                "source_url": None,
                "servings": 1,
                "prep_time_minutes": 5,
                "cook_time_minutes": 2,
                "meal_types": ["breakfast"],
                "ingredients": [
                    {"name": "bread", "amount": 1, "unit": "slice", "notes": None, "optional": False}
                ],
                "steps": [{"instruction": "Toast the bread.", "timer_minutes": 2}],
                "dietary_tags": [],
                "detected_allergens": ["wheat"],
                "calories": 120,
                "protein_grams": 4,
                "carbs_grams": 22,
                "fat_grams": 2,
                "total_cost_minor": 75,
                "cost_per_serving_minor": 75,
                "currency_code": "USD",
            },
            "inferred_fields": inferred_fields or [],
        }
    )


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": recipe_response()}]}}]}


class FakeClient:
    def __init__(self):
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, endpoint, **kwargs):
        self.request = (endpoint, kwargs)
        return FakeResponse()


class GeminiTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_uses_header_auth_and_structured_output(self):
        fake_client = FakeClient()
        with (
            patch.object(gemini.settings, "gemini_api_key", "test-key"),
            patch.object(gemini.httpx, "AsyncClient", return_value=fake_client),
        ):
            content = await gemini._generate("gemini-test", "system", [{"text": "recipe"}])

        self.assertEqual(content, recipe_response())
        endpoint, request = fake_client.request
        self.assertTrue(endpoint.endswith("/models/gemini-test:generateContent"))
        self.assertEqual(request["headers"]["x-goog-api-key"], "test-key")
        generation = request["json"]["generationConfig"]
        self.assertEqual(generation["responseMimeType"], "application/json")
        self.assertEqual(generation["thinkingConfig"]["thinkingBudget"], 0)
        self.assertIn("recipe", generation["responseJsonSchema"]["properties"])

    async def test_normalize_marks_inferred_fields_as_lower_confidence(self):
        with (
            patch.object(gemini.settings, "gemini_api_key", "test-key"),
            patch.object(gemini, "_generate", new=AsyncMock(return_value=recipe_response(["servings"]))),
        ):
            draft, confidence, warnings = await gemini.normalize_recipe_text(
                "1 slice bread. Toast it.",
                ExtractionMethod.manual_entry,
            )

        self.assertEqual(draft.title, "Tomato Toast")
        self.assertEqual(confidence["servings"], 0.45)
        self.assertEqual(confidence["title"], 0.78)
        self.assertTrue(any("Gemini completed" in warning for warning in warnings))

    async def test_normalize_without_key_fails_without_network_call(self):
        with (
            patch.object(gemini.settings, "gemini_api_key", None),
            patch.object(gemini, "_generate", new=AsyncMock()) as generate,
        ):
            draft, confidence, warnings = await gemini.normalize_recipe_text(
                "1 slice bread. Toast it.",
                ExtractionMethod.manual_entry,
            )

        self.assertIsNone(draft)
        self.assertEqual(confidence, {})
        self.assertIn("not configured", warnings[0])
        generate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
