# Pinchmeal recipe-import service

This is a FastAPI web service, not a Google Cloud Function. It extracts recipe information from websites and social captions, then uses Qwen to prepare structured recipe drafts.
For social imports, Qwen may complete missing culinary fields using the creator caption and public thumbnail. Imported recipes must still be reviewed before saving. It never marks a recipe allergen-safe from missing information.

Recipe drafts also include per-serving calories, protein, carbohydrates and fat, plus total and per-serving cost in USD cents. Qwen calculates these values from the final ingredient quantities and serving count when the source does not provide them.

## The only required secret

`QWEN_API_KEY` is the only secret required for recipe extraction. Create it in Alibaba Cloud Model Studio in the **Singapore region**. The included default endpoint is the Singapore endpoint, and Qwen keys must match the endpoint region.

`COGNIFY_API_KEY` is optional and enables background imagery for Qwen-generated meal plans. It is the RapidAPI key for CognifyAPI's Google Images API. Keep it in the backend only. Image lookup uses the recipe title exactly, returns several candidates, and does not delay Qwen plan generation.

Do not put the Qwen key in the iOS app. It belongs only in local `.env` during development and in Google Secret Manager on Cloud Run.

## Local setup

1. Duplicate `.env.example` and rename the copy to `.env`.
2. Paste the Model Studio key after `QWEN_API_KEY=`. Do not add quotation marks.
3. To test generated-meal imagery, subscribe to CognifyAPI on RapidAPI and paste that RapidAPI key after `COGNIFY_API_KEY=`.
4. Leave the provider URLs and hosts unchanged.
5. Install `requirements.txt` and run `uvicorn main:app --reload`.
6. Open `http://127.0.0.1:8000/health`. It should return `{"status":"ok","version":"1.0.0"}`.

`API_AUTH_TOKEN` is optional during a private initial test. Before sharing the deployed endpoint, create a random value and set the same value in the iOS `PINCHMEAL_API_TOKEN` build setting.

## Cloud Run

Use the detailed field-by-field guide in [CLOUD_RUN_SETUP.md](CLOUD_RUN_SETUP.md). The important choices are:

- Deployment type: **Cloud Run Service**, not Cloud Run Function.
- Build type: **Docker**.
- Build context directory: **`.`** because this repository’s root contains the Dockerfile.
- Dockerfile: **`Dockerfile`**.
- Entry point: leave blank.
- Function target: leave blank.

The Dockerfile already launches FastAPI with Gunicorn on Cloud Run’s `PORT`.

## Endpoints

- `GET /health`
- `POST /v1/imports/recipe`
- `POST /v1/imports/recipe-image` (optional server-side image flow; the iOS app normally sends on-device OCR text)
- `POST /v1/images/recipe` (background Google Images candidates for generated recipes)

The service logs request IDs, route, status and duration. It does not log recipe text, private URLs, API keys or credentials.
