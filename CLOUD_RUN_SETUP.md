# Cloud Run setup (comparison deployment)

Pinchmeal is a complete FastAPI web service with a Dockerfile. In Google Cloud choose **Cloud Run → Services → Create/Deploy service**. Do not choose a Cloud Run Function.

## Build settings

| Console field | Exact value |
|---|---|
| Build type | `Docker` |
| Build context directory | `.` |
| Dockerfile path | `Dockerfile` |
| Entry point | Leave blank |
| Function target | Leave blank |

## Recommended service settings

| Setting | Value |
|---|---|
| Region | Nearest region to most app users |
| Authentication | Allow unauthenticated invocations |
| Container port | `8080` |
| CPU | `1` |
| Memory | `1 GiB` |
| Minimum instances | `0` |
| Maximum instances | `3` |
| Concurrency | `4` |
| Request timeout | `120 seconds` |
| Billing | Request-based |

Unauthenticated Cloud Run invocation is required because the iOS app is not signed into Google Cloud. `API_AUTH_TOKEN` provides basic application-level protection.

## Variables and secrets

Create `gemini-api-key` in Secret Manager and attach it as `GEMINI_API_KEY`. Optionally create secrets for `COGNIFY_API_KEY` and `API_AUTH_TOKEN`.

Add these ordinary environment variables:

| Name | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `EXPOSE_DOCS` | `false` |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta` |
| `GEMINI_TEXT_MODEL` | `gemini-2.5-flash-lite` |
| `GEMINI_VISION_MODEL` | `gemini-2.5-flash-lite` |
| `GEMINI_TIMEOUT_SECONDS` | `90` |
| `WEB_CONCURRENCY` | `1` |
| `GUNICORN_TIMEOUT` | `120` |

## Verify

Open `https://YOUR-CLOUD-RUN-URL/health`. Expected response:

```json
{"status":"ok","version":"1.0.0"}
```

Then set the iOS `PINCHMEAL_BACKEND_BASE_URL` build setting to the Cloud Run service URL without an endpoint path.

Keep minimum instances at zero for the cost comparison. Record both cold and warm request latency because scale-to-zero startup time materially affects the result.
