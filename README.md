# Pinchmeal recipe-import service

This is a FastAPI web service, not a Google Cloud Function. It extracts recipe information from websites and social captions, then uses Qwen to prepare structured recipe drafts.
For social imports, Qwen may complete missing culinary fields using the creator caption and public thumbnail. These estimates are returned with lower confidence and must be reviewed before saving. It never marks a recipe allergen-safe from missing information.

## The only required secret

`QWEN_API_KEY` is the only secret required to start the service. Create it in Alibaba Cloud Model Studio in the **Singapore region**. The included default endpoint is the Singapore endpoint, and Qwen keys must match the endpoint region.

Do not put the Qwen key in the iOS app. It belongs only in local `.env` during development and in Google Secret Manager on Cloud Run.

## Local setup

1. Duplicate `.env.example` and rename the copy to `.env`.
2. Paste the Model Studio key after `QWEN_API_KEY=`. Do not add quotation marks.
3. Leave the other Qwen values unchanged for a Singapore key.
4. Install `requirements.txt` and run `uvicorn main:app --reload`.
5. Open `http://127.0.0.1:8000/health`. It should return `{"status":"ok","version":"1.0.0"}`.

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

The service logs request IDs, route, status and duration. It does not log recipe text, private URLs, API keys or credentials.
