# Cloudflare Containers trial

Cloudflare Containers runs the existing FastAPI Docker image, so the trial preserves `yt-dlp`, Instaloader, image handling, and the exact API response contract. A plain Worker rewrite is not used because those Python dependencies need a normal Linux container.

## What is preconfigured

- Worker entry point: `src/index.js`
- Container image: the repository's existing `Dockerfile`
- Instance type: `basic` (1 GiB memory)
- Placement: APAC
- Active pool: one stateless instance for the initial low-traffic trial
- Maximum running instances: three
- Idle shutdown: ten minutes

Cloudflare currently routes stateless containers through a fixed pool rather than built-in automatic autoscaling. To test more concurrency, increase `INSTANCE_COUNT` in `src/index.js`, keeping it at or below `max_instances` in `wrangler.jsonc`.

## Prerequisites

1. Enable the Workers Paid plan; Containers are not included on Workers Free.
2. Install a current Node.js release supported by Wrangler.
3. Have Docker Desktop or another Docker-compatible engine running for local deployments. Workers Builds can build the Dockerfile remotely instead.
4. Create a Gemini API key in Google AI Studio.

## Install and authenticate

From the repository root:

```bash
npm install
npx wrangler login
```

## Add secrets

Add the Gemini key:

```bash
npx wrangler secret put GEMINI_API_KEY
```

Before connecting a distributed app build, add an application token:

```bash
npx wrangler secret put API_AUTH_TOKEN
```

If recipe image search is enabled, also run:

```bash
npx wrangler secret put COGNIFY_API_KEY
```

The Worker passes these secret bindings to the container as environment variables. Do not add secret values to `wrangler.jsonc` or source control.

## Deploy

Validate the Worker configuration without requiring Docker:

```bash
npm run check
```

Then deploy the Worker and container image:

```bash
npm run deploy
```

The first deployment can take several minutes while Cloudflare builds and provisions the image. The command returns a URL similar to:

`https://pinchmeal-recipe-import.YOUR-SUBDOMAIN.workers.dev`

Check it with:

```bash
curl https://YOUR-WORKER-URL/health
```

Expected response:

```json
{"status":"ok","version":"1.0.0"}
```

Set the iOS `PINCHMEAL_BACKEND_BASE_URL` build setting to the Worker URL without an endpoint path.

## Compare with Cloud Run

Run at least 20 imports against each service using the same URLs and network, recording:

- cold latency after at least ten minutes idle;
- warm latency for immediate repeats;
- success rate by Instagram, TikTok, YouTube, and website;
- Gemini token cost (the same for both hosts when prompts and models match);
- Cloudflare container/Worker/Durable Object cost versus Cloud Run compute and egress.

Do not infer the winner from `/health` alone. Most import time is spent fetching the social source and waiting for Gemini, so the edge entry point may have only a small effect on end-to-end latency.

After both hosts are deployed, `benchmark_hosts.py` alternates requests between them and reports mean, p50, p95, and successful-import counts:

```bash
python benchmark_hosts.py \
  --cloud-run https://YOUR-CLOUD-RUN-URL \
  --cloudflare https://YOUR-WORKER-URL \
  --source-url https://A-PUBLIC-SOCIAL-RECIPE-URL \
  --source-type social \
  --runs 20
```

Add `--token YOUR_API_AUTH_TOKEN` when application-level authentication is enabled. Run the benchmark once after both services have been idle to capture cold behavior, then immediately again for warm behavior.
