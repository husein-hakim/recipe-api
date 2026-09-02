# Cloud Run setup — exact console fields

## First: this is a Service, not a Function

The Pinchmeal backend is a complete FastAPI web service with its own Dockerfile. In Google Cloud choose **Cloud Run → Services → Create/Deploy service**. Do not choose “Write a function” or “Cloud Run function.” A function deployment asks for a function target because it expects one Python function; Pinchmeal instead starts the whole FastAPI application.

If your current page cannot switch away from “Function,” return to the Cloud Run overview and start a new **Service** deployment.

## 1. Prepare Qwen

1. Open Alibaba Cloud Model Studio.
2. Select the **Singapore** region.
3. Activate Model Studio if prompted.
4. Open API keys and create a key for your workspace.
5. Copy the key. It normally begins with `sk-`.

The repository defaults to the Singapore-compatible endpoint:

`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`

Model Studio also offers a newer workspace-specific Singapore URL. Either works. If you use the workspace-specific URL, copy it from Workspace Details and use it as `QWEN_BASE_URL`. The API key and endpoint must be from the same region.

## 2. Create the Google secret

In Google Cloud Console:

1. Open **Security → Secret Manager**.
2. Choose **Create secret**.
3. Name: `qwen-api-key`.
4. Secret value: paste the Qwen API key only.
5. Create it.

Do not upload a `.env` file to Cloud Run. Cloud Run receives settings through its Variables & Secrets screen.

## 3. Build settings

On the Cloud Run Service source/build screen enter:

| Console field | Exact value |
|---|---|
| Build type | `Docker` |
| Build context directory | `.` |
| Dockerfile path | `Dockerfile` |
| Entry point | Leave blank |
| Function target | Leave blank |

Why the context is `.`: `/Users/husein/recipe` is already the repository root and the Dockerfile is directly inside it. If you later place this backend inside a larger repository under a folder named `recipe`, the context would become `recipe` instead.

Do not choose Python buildpacks for this deployment. Python buildpacks/function mode is what creates the confusing entry-point and function-target fields.

## 4. Service settings

Recommended initial values:

| Setting | Value |
|---|---|
| Region | `asia-southeast1` (Singapore) |
| Authentication | Allow unauthenticated invocations |
| Container port | `8080` |
| CPU | `1` |
| Memory | `1 GiB` |
| Minimum instances | `0` |
| Maximum instances | `3` |
| Concurrency | `4` |
| Request timeout | `120 seconds` |
| Billing | Request-based |

Unauthenticated invocation is needed because the iOS app is not signed into Google Cloud. Application-level protection is handled separately with `API_AUTH_TOKEN`; App Attest/API Gateway can replace that later.

## 5. Variables and secrets

Open the service’s **Variables & Secrets** section.

Add this secret reference:

| Variable name | Source | Value |
|---|---|---|
| `QWEN_API_KEY` | Secret | `qwen-api-key`, version `latest` |

Add these ordinary environment variables:

| Name | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `EXPOSE_DOCS` | `false` |
| `QWEN_BASE_URL` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| `QWEN_TEXT_MODEL` | `qwen-flash` |
| `QWEN_VISION_MODEL` | `qwen3-vl-plus` |
| `QWEN_TIMEOUT_SECONDS` | `90` |
| `WEB_CONCURRENCY` | `1` |
| `GUNICORN_TIMEOUT` | `120` |

All other limits already have safe defaults in `config.py`; you do not need to enter them in Cloud Run.

### Optional API token

For the first private health check you may omit `API_AUTH_TOKEN`. Before connecting a distributed build of the app:

1. Generate a random value locally with `openssl rand -hex 32`.
2. Store it in Secret Manager as `pinchmeal-api-token`.
3. Attach it to Cloud Run with variable name `API_AUTH_TOKEN`.
4. Put the same value in the iOS build setting `PINCHMEAL_API_TOKEN`.

This token is basic abuse protection, not an administrative Qwen credential. Never put `QWEN_API_KEY` in the app.

## 6. Deploy and check it

After deployment Cloud Run gives you a URL such as:

`https://pinchmeal-import-xxxxx.asia-southeast1.run.app`

Open:

`https://YOUR-CLOUD-RUN-URL/health`

Expected response:

```json
{"status":"ok","version":"1.0.0"}
```

Then test a public recipe page:

```bash
curl -X POST 'https://YOUR-CLOUD-RUN-URL/v1/imports/recipe' \
  -H 'Content-Type: application/json' \
  -d '{"source_type":"website","url":"https://example.com/a-public-recipe"}'
```

If you enabled `API_AUTH_TOKEN`, also add:

```bash
-H 'X-Pinchmeal-API-Token: YOUR_TOKEN'
```

Finally set the iOS build setting `PINCHMEAL_BACKEND_BASE_URL` to the Cloud Run service URL without `/v1/imports/recipe`; the app adds that path itself.

## Common errors

- **`developerconnect.gitRepositoryLinks.fetchReadToken` denied during `FETCHSOURCE`:** open the failed build in **Cloud Build → History**, copy the service account shown in its build details, then grant that exact service account **Developer Connect Read Token Accessor** (`roles/developerconnect.readTokenAccessor`) in **IAM & Admin → IAM**. Retry after the IAM change has propagated. Do not guess between the legacy Cloud Build and Compute Engine default service accounts; Google projects can use either.
- **Function target required:** you started a Function deployment. Create a Cloud Run Service and choose Docker.
- **Dockerfile not found:** context must be `.` when the selected repository is `/Users/husein/recipe`.
- **Qwen 401 / incorrect API key:** the Qwen key and `QWEN_BASE_URL` are from different regions.
- **Qwen 404:** verify the base URL ends in `/compatible-mode/v1` and the model names are available in your Model Studio workspace.
- **Cloud Run starts then stops:** confirm the container port is `8080`; do not override the Docker command or entry point.
- **Import returns unauthorized:** `API_AUTH_TOKEN` is set on Cloud Run but missing or different in the request/app build setting.
- **Costs rise unexpectedly:** keep max instances at 3, configure Google billing alerts, and monitor Model Studio token usage. Neither Cloud Run nor Qwen is guaranteed to remain free beyond its allowances.
