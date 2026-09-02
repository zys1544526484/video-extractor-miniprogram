from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from ..errors import AppError

Resolver = Callable[[str], Awaitable[list[str]]]


async def resolve_host(host: str) -> list[str]:
    def lookup() -> list[str]:
        values = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return sorted({item[4][0] for item in values})

    try:
        return await asyncio.to_thread(lookup)
    except socket.gaierror as error:
        raise AppError("URL_INVALID", "目标域名无法解析", retryable=True) from error


def is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global


async def validate_public_url(url: str, resolver: Resolver = resolve_host) -> tuple[str, list[str]]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise AppError("URL_INVALID", "链接格式无效") from error
    if parsed.scheme not in {"http", "https"}:
        raise AppError("URL_INVALID", "只支持 HTTP 或 HTTPS 链接")
    if not parsed.hostname or parsed.username or parsed.password:
        raise AppError("URL_INVALID", "链接主机无效")
    if port is not None and not (1 <= port <= 65535):
        raise AppError("URL_INVALID", "链接端口无效")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise AppError("URL_INVALID", "不允许访问本机地址")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        addresses = await resolver(host)
    else:
        addresses = [str(literal)]
    if not addresses or any(not is_public_ip(address) for address in addresses):
        raise AppError("URL_INVALID", "不允许访问内网、本机或保留地址")
    return host, addresses

