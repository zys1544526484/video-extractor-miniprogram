from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

from ..errors import AppError
from .yt_dlp_adapter import YtDlpAdapter

_ORIGINAL_GETADDRINFO = socket.getaddrinfo


def guarded_getaddrinfo(
    host: str | bytes | None,
    port: str | int | None,
    family: int = 0,
    type: int = 0,
    proto: int = 0,
    flags: int = 0,
) -> list[tuple[Any, ...]]:
    results = _ORIGINAL_GETADDRINFO(host, port, family, type, proto, flags)
    addresses = {str(item[4][0]).split("%", 1)[0] for item in results}
    try:
        public = bool(addresses) and all(ipaddress.ip_address(value).is_global for value in addresses)
    except ValueError:
        public = False
    if not public:
        raise OSError("yt-dlp network target is not a public IP address")
    return results


def apply_resource_limits(max_video_bytes: int, timeout_seconds: int) -> None:
    if os.name == "nt":
        return
    try:
        import resource
    except ImportError:
        return
    file_limit = max_video_bytes
    memory_limit = max(512 * 1024 * 1024, min(1024 * 1024 * 1024, max_video_bytes * 4))
    cpu_limit = max(5, timeout_seconds + 5)
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def validate_initial_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise AppError("PARSE_FAILED", "平台链接格式无效") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise AppError("PARSE_FAILED", "平台链接格式无效")


def run(payload: dict[str, Any]) -> dict[str, Any]:
    settings_data = payload.get("settings") or {}
    url = str(payload.get("url") or "")
    platform = str(payload.get("platform") or "")
    download_media = bool(payload.get("download_media"))
    requested_quality = str(payload.get("requested_quality") or "original")
    validate_initial_url(url)

    settings = SimpleNamespace(
        temp_dir=Path(str(settings_data["temp_dir"])),
        max_video_bytes=int(settings_data["max_video_bytes"]),
        http_timeout_seconds=int(settings_data["http_timeout_seconds"]),
    )
    timeout_seconds = int(settings_data["parse_timeout_seconds"])
    apply_resource_limits(settings.max_video_bytes, timeout_seconds)

    os.environ["YTDLP_NO_PLUGINS"] = "1"
    socket.getaddrinfo = guarded_getaddrinfo
    result = YtDlpAdapter(settings)._extract_sync(
        url,
        platform,
        download_media,
        requested_quality,
    )
    return {"ok": True, "result": result.model_dump(mode="json")}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read(64 * 1024).decode("utf-8"))
        response = run(payload)
    except AppError as error:
        response = {
            "ok": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        response = {
            "ok": False,
            "error": {
                "code": "PARSE_FAILED",
                "message": "平台解析进程输入无效",
                "retryable": False,
            },
        }
    except Exception:
        response = {
            "ok": False,
            "error": {
                "code": "PARSE_FAILED",
                "message": "平台解析进程异常",
                "retryable": True,
            },
        }
    encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
