from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class YTDLPMetadata:
    description: str
    publisher: str | None
    thumbnail_url: str | None


class YTDLPMetadataError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def extract_ytdlp_metadata(url: str) -> YTDLPMetadata:
    """Read public post metadata without downloading its video or audio."""

    def load() -> dict[str, Any]:
        import yt_dlp

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "cachedir": False,
            "socket_timeout": 20,
            "retries": 1,
            "extractor_retries": 1,
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            result = downloader.extract_info(url, download=False)
        if not isinstance(result, dict):
            raise YTDLPMetadataError("empty_response")
        return result

    try:
        info = await asyncio.to_thread(load)
    except YTDLPMetadataError:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "private" in message or "login" in message or "sign in" in message or "cookies" in message:
            reason = "authentication_required"
        elif "unsupported url" in message:
            reason = "unsupported"
        elif "deleted" in message or "unavailable" in message or "not available" in message:
            reason = "unavailable"
        elif "timed out" in message or "timeout" in message:
            reason = "timeout"
        else:
            reason = "extractor_failed"
        raise YTDLPMetadataError(reason) from exc

    description = str(info.get("description") or info.get("title") or "").strip()
    publisher = info.get("channel") or info.get("uploader") or info.get("creator") or info.get("uploader_id")
    thumbnail = info.get("thumbnail")
    return YTDLPMetadata(
        description=description,
        publisher=str(publisher).strip() if publisher else None,
        thumbnail_url=str(thumbnail).strip() if thumbnail else None,
    )
