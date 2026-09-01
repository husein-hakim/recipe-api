from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from config import settings
from models import ErrorCode


class SafeFetchError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


async def validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SafeFetchError(ErrorCode.unsupported_url, "Only public HTTP and HTTPS links are supported.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise SafeFetchError(ErrorCode.unsafe_url, "Local network links cannot be imported.")
    try:
        addresses = await asyncio.get_running_loop().run_in_executor(None, lambda: socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM))
    except socket.gaierror as exc:
        raise SafeFetchError(ErrorCode.source_unavailable, "The source address could not be found.") from exc
    for entry in addresses:
        address = ipaddress.ip_address(entry[4][0])
        if not address.is_global or address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise SafeFetchError(ErrorCode.unsafe_url, "Local or reserved network links cannot be imported.")


async def safe_fetch(url: str) -> tuple[str, bytes, str]:
    current = url
    timeout = httpx.Timeout(settings.request_timeout_seconds, connect=min(10.0, settings.request_timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"User-Agent": settings.user_agent}) as client:
        for redirect_count in range(settings.maximum_redirects + 1):
            await validate_public_url(current)
            try:
                async with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count == settings.maximum_redirects:
                            raise SafeFetchError(ErrorCode.source_unavailable, "The source redirected too many times.")
                        current = urljoin(current, location)
                        continue
                    if response.status_code in {401, 403}:
                        raise SafeFetchError(ErrorCode.private_source, "This source is private or requires sign-in.")
                    if response.status_code in {404, 410}:
                        raise SafeFetchError(ErrorCode.deleted_source, "This source is unavailable or was deleted.")
                    if response.status_code >= 400:
                        raise SafeFetchError(ErrorCode.source_unavailable, "The source could not be opened.")
                    declared = response.headers.get("content-length")
                    if declared and int(declared) > settings.maximum_response_bytes:
                        raise SafeFetchError(ErrorCode.response_too_large, "The source is too large to import safely.")
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > settings.maximum_response_bytes:
                            raise SafeFetchError(ErrorCode.response_too_large, "The source is too large to import safely.")
                        chunks.append(chunk)
                    return str(response.url), b"".join(chunks), response.headers.get("content-type", "")
            except httpx.TimeoutException as exc:
                raise SafeFetchError(ErrorCode.timeout, "The source took too long to respond.") from exc
            except httpx.RequestError as exc:
                raise SafeFetchError(ErrorCode.source_unavailable, "The source could not be reached.") from exc
    raise SafeFetchError(ErrorCode.source_unavailable, "The source could not be opened.")
