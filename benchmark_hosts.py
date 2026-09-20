from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass

import httpx


@dataclass
class Result:
    host: str
    duration_ms: float
    http_status: int | None
    import_status: str | None
    error: str | None = None


async def request_once(
    client: httpx.AsyncClient,
    name: str,
    base_url: str,
    payload: dict[str, str],
    token: str | None,
) -> Result:
    headers = {"X-Pinchmeal-API-Token": token} if token else {}
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url.rstrip('/')}/v1/imports/recipe",
            json=payload,
            headers=headers,
        )
        duration_ms = (time.perf_counter() - started) * 1_000
        body = response.json()
        return Result(name, duration_ms, response.status_code, body.get("status"), body.get("error_code"))
    except Exception as exc:
        return Result(name, (time.perf_counter() - started) * 1_000, None, None, type(exc).__name__)


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percent)
    return ordered[index]


def summarize(results: list[Result]) -> dict[str, object]:
    durations = [result.duration_ms for result in results]
    successful = [result for result in results if result.http_status == 200 and result.import_status in {"complete", "incomplete"}]
    return {
        "requests": len(results),
        "successful_imports": len(successful),
        "mean_ms": round(statistics.fmean(durations), 1),
        "p50_ms": round(percentile(durations, 0.50), 1),
        "p95_ms": round(percentile(durations, 0.95), 1),
        "errors": [result.error for result in results if result.error],
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Pinchmeal import latency across two deployments.")
    parser.add_argument("--cloud-run", required=True, help="Cloud Run base URL")
    parser.add_argument("--cloudflare", required=True, help="Cloudflare Worker base URL")
    parser.add_argument("--source-url", required=True, help="One public recipe or social URL used for every request")
    parser.add_argument("--source-type", choices=["website", "social"], default="social")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--token", help="Optional X-Pinchmeal-API-Token value")
    args = parser.parse_args()

    if args.runs < 1:
        parser.error("--runs must be at least 1")

    deployments = [("cloud_run", args.cloud_run), ("cloudflare", args.cloudflare)]
    collected: dict[str, list[Result]] = {name: [] for name, _ in deployments}
    payload = {"source_type": args.source_type, "url": args.source_url}

    async with httpx.AsyncClient(timeout=150) as client:
        for run in range(args.runs):
            ordered = deployments if run % 2 == 0 else list(reversed(deployments))
            for name, base_url in ordered:
                result = await request_once(client, name, base_url, payload, args.token)
                collected[name].append(result)
                print(f"{name} run={run + 1} duration_ms={result.duration_ms:.1f} status={result.import_status or result.http_status} error={result.error or '-'}")

    print(json.dumps({name: summarize(results) for name, results in collected.items()}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
