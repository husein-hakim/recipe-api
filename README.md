# Pinchmeal recipe-import service

This FastAPI service extracts recipe information from websites and public Instagram, TikTok, and YouTube metadata, then uses the Gemini API to prepare structured recipe drafts.

For social imports, Gemini may complete missing culinary fields using the creator caption and public thumbnail. Imported recipes must still be reviewed before saving. The service never treats missing allergen information as proof that a recipe is allergen-safe.

Recipe drafts include per-serving calories, protein, carbohydrates and fat, plus total and per-serving cost in USD cents. Gemini calculates these values from the final ingredient quantities and serving count when the source does not provide them.

## Required secret

`GEMINI_API_KEY` is the only secret required for recipe extraction. Create it in Google AI Studio. Keep it in the backend only—never put it in the iOS app.

`COGNIFY_API_KEY` is optional and enables background imagery for generated meal plans. It is the RapidAPI key for CognifyAPI's Google Images API.

`API_AUTH_TOKEN` is optional during a private test. Before sharing a deployed endpoint, create a random value and set the same value in the iOS `PINCHMEAL_API_TOKEN` build setting.

## Local setup

1. Duplicate `.env.example` as `.env`.
2. Add your Google AI Studio key after `GEMINI_API_KEY=`.
3. Install `requirements.txt`.
4. Run `uvicorn main:app --reload`.
5. Open `http://127.0.0.1:8000/health`; it should return `{"status":"ok","version":"1.0.0"}`.

The defaults use the stable multimodal `gemini-2.5-flash-lite` model for both text and image normalization. `GEMINI_VISION_MODEL` remains separate so a stronger image model can be tested later without changing code.

## Deployments

- Use [CLOUDFLARE_SETUP.md](CLOUDFLARE_SETUP.md) to run the existing Docker service in Cloudflare Containers for the speed/cost trial.
- Use [CLOUD_RUN_SETUP.md](CLOUD_RUN_SETUP.md) if you want to retain Cloud Run as the control deployment.

Both deployments use the same Dockerfile and API contract, making side-by-side latency and cost measurements meaningful.

## Endpoints

- `GET /health`
- `POST /v1/imports/recipe`
- `POST /v1/imports/recipe-image` (optional server-side image flow; the iOS app normally sends on-device OCR text)
- `POST /v1/images/recipe` (background Google Images candidates for generated recipes)

The service logs request IDs, route, status and duration. It does not log recipe text, private URLs, API keys or credentials.
