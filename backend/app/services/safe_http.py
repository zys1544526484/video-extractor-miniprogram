from __future__ import annotations

import ipaddress
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import aiohttp
import httpx
from aiohttp.abc import AbstractResolver, ResolveResult

from ..errors import AppError
from ..security.ssrf import Resolver, is_public_ip, resolve_host, validate_public_url

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MEDIA_CONTENT_TYPES = {
    "application/octet-stream",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
}
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
DEFAULT_MAX_IMAGE_BYTES = 20 * 1024 * 1024


class PinnedPublicResolver(AbstractResolver):
    """Resolve to checked public IPs and hand those exact IPs to the connector."""

    def __init__(self, resolver: Resolver) -> None:
        self.resolver = resolver

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> list[ResolveResult]:
        addresses = await self.resolver(host)
        if not addresses or any(not is_public_ip(address) for address in addresses):
            raise AppError("URL_INVALID", "不允许访问内网、本机或保留地址")
        results: list[ResolveResult] = []
        for address in addresses:
            parsed = ipaddress.ip_address(address)
            address_family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
            if family not in {socket.AF_UNSPEC, address_family}:
                continue
            results.append(
                ResolveResult(
                    hostname=host,
                    host=address,
                    port=port,
                    family=address_family,
                    proto=socket.IPPROTO_TCP,
                    flags=socket.AI_NUMERICHOST,
                )
            )
        if not results:
            raise AppError("URL_INVALID", "目标域名没有可用的公网地址")
        return results

    async def close(self) -> None:
        return None


@dataclass
class AioHttpResponseAdapter:
    response: aiohttp.ClientResponse

    @property
    def status_code(self) -> int:
        return self.response.status

    @property
    def headers(self) -> Mapping[str, str]:
        return self.response.headers

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        async for chunk in self.response.content.iter_chunked(64 * 1024):
            yield chunk

    async def aclose(self) -> None:
        self.response.release()
        await self.response.wait_for_close()


@dataclass
class OpenedStream:
    response: Any
    final_url: str
    close_callback: Callable[[], Awaitable[None]]

    async def close(self) -> None:
        await self.close_callback()


class SafeHttpClient:
    def __init__(
        self,
        *,
        timeout_seconds: int,
        max_redirects: int,
        max_video_bytes: int,
        max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
        resolver: Resolver = resolve_host,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.httpx_timeout = httpx.Timeout(timeout_seconds)
        self.max_redirects = max_redirects
        self.max_video_bytes = max_video_bytes
        self.max_image_bytes = max_image_bytes
        self.resolver = resolver
        self.transport = transport

    async def validate_url(self, url: str) -> tuple[str, list[str]]:
        return await validate_public_url(url, self.resolver)

    def _httpx_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.httpx_timeout,
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
            headers={"User-Agent": "VideoExtractor/0.1 (+public-media-parser)"},
        )

    def _aiohttp_session(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(
            resolver=PinnedPublicResolver(self.resolver),
            use_dns_cache=False,
            force_close=True,
            limit=20,
            ssl=True,
        )
        return aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(
                total=None,
                connect=self.timeout_seconds,
                sock_connect=self.timeout_seconds,
                sock_read=self.timeout_seconds,
            ),
            trust_env=False,
            headers={"User-Agent": "VideoExtractor/0.1 (+public-media-parser)"},
        )

    @staticmethod
    def _raise_for_status(status: int, allowed: set[int]) -> None:
        if status < 400 or status in allowed:
            return
        inaccessible = status in {401, 403, 404}
        raise AppError(
            "CONTENT_NOT_PUBLIC" if inaccessible else "UPSTREAM_TIMEOUT",
            "该内容不可公开访问" if inaccessible else "上游服务暂时不可用",
            retryable=status >= 500,
        )

    async def _request_httpx(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None,
        read_limit: int,
        allowed_error_statuses: set[int],
    ) -> tuple[str, Mapping[str, str], int, bytes]:
        current = url
        async with self._httpx_client() as client:
            for redirect_count in range(self.max_redirects + 1):
                await self.validate_url(current)
                try:
                    async with client.stream(method, current, headers=headers) as response:
                        if response.status_code in REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if not location or redirect_count >= self.max_redirects:
                                raise AppError("UPSTREAM_TIMEOUT", "上游重定向过多", retryable=True)
                            current = urljoin(current, location)
                            continue
                        self._raise_for_status(response.status_code, allowed_error_statuses)
                        body = bytearray()
                        if method != "HEAD":
                            async for chunk in response.aiter_bytes():
                                body.extend(chunk)
                                if read_limit and len(body) > read_limit:
                                    raise AppError("MEDIA_TOO_LARGE", "上游响应超过允许大小")
                        return current, response.headers, response.status_code, bytes(body)
                except httpx.TimeoutException as error:
                    raise AppError("UPSTREAM_TIMEOUT", "上游请求超时", retryable=True) from error
                except httpx.NetworkError as error:
                    raise AppError("UPSTREAM_TIMEOUT", "上游网络连接失败", retryable=True) from error
        raise AppError("UPSTREAM_TIMEOUT", "上游重定向失败", retryable=True)

    async def _request_aiohttp(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None,
        read_limit: int,
        allowed_error_statuses: set[int],
    ) -> tuple[str, Mapping[str, str], int, bytes]:
        current = url
        async with self._aiohttp_session() as session:
            for redirect_count in range(self.max_redirects + 1):
                await self.validate_url(current)
                try:
                    async with session.request(
                        method,
                        current,
                        headers=headers,
                        allow_redirects=False,
                    ) as response:
                        if response.status in REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if not location or redirect_count >= self.max_redirects:
                                raise AppError("UPSTREAM_TIMEOUT", "上游重定向过多", retryable=True)
                            current = urljoin(current, location)
                            continue
                        self._raise_for_status(response.status, allowed_error_statuses)
                        body = bytearray()
                        if method != "HEAD":
                            async for chunk in response.content.iter_chunked(64 * 1024):
                                body.extend(chunk)
                                if read_limit and len(body) > read_limit:
                                    raise AppError("MEDIA_TOO_LARGE", "上游响应超过允许大小")
                        return current, response.headers, response.status, bytes(body)
                except TimeoutError as error:
                    raise AppError("UPSTREAM_TIMEOUT", "上游请求超时", retryable=True) from error
                except aiohttp.ClientError as error:
                    raise AppError("UPSTREAM_TIMEOUT", "上游网络连接失败", retryable=True) from error
        raise AppError("UPSTREAM_TIMEOUT", "上游重定向失败", retryable=True)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        read_limit: int = 0,
        allowed_error_statuses: set[int] | None = None,
    ) -> tuple[str, Mapping[str, str], int, bytes]:
        arguments = {
            "headers": headers,
            "read_limit": read_limit,
            "allowed_error_statuses": allowed_error_statuses or set(),
        }
        if self.transport is not None:
            return await self._request_httpx(method, url, **arguments)
        return await self._request_aiohttp(method, url, **arguments)

    async def get_text(
        self,
        url: str,
        *,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> tuple[str, str, dict[str, str]]:
        final_url, headers, _, body = await self._request("GET", url, read_limit=max_bytes)
        content_type = headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type and "json" not in content_type:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", "目标页面不是可解析的公开网页")
        encoding = "utf-8"
        if "charset=" in content_type:
            encoding = content_type.rsplit("charset=", 1)[-1].split(";", 1)[0].strip()
        return final_url, body.decode(encoding, errors="replace"), dict(headers)

    @staticmethod
    def _declared_size(headers: Mapping[str, str]) -> int | None:
        content_length = headers.get("content-length")
        if content_length and content_length.isdigit():
            return int(content_length)
        content_range = headers.get("content-range", "")
        if "/" in content_range:
            total = content_range.rsplit("/", 1)[-1]
            if total.isdigit():
                return int(total)
        return None

    async def _probe_resource(
        self,
        url: str,
        headers: dict[str, str] | None,
        *,
        allowed_content_types: set[str],
        max_bytes: int,
        kind_label: str,
    ) -> dict[str, Any]:
        final_url, response_headers, status, _ = await self._request(
            "HEAD",
            url,
            headers=headers,
            allowed_error_statuses={405},
        )
        if status == 405:
            final_url, response_headers, _, _ = await self._request(
                "GET",
                url,
                headers={**(headers or {}), "Range": "bytes=0-0"},
                read_limit=64 * 1024,
            )
        content_type = response_headers.get("content-type", "application/octet-stream").split(";", 1)[0]
        size = self._declared_size(response_headers)
        if size and size > max_bytes:
            raise AppError("MEDIA_TOO_LARGE", f"源{kind_label}超过服务器可处理上限")
        if kind_label == "图片":
            valid_type = content_type in allowed_content_types
        else:
            valid_type = content_type.startswith("video/") or content_type in allowed_content_types
        if not valid_type:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", f"目标资源不是受支持的{kind_label}格式")
        return {"url": final_url, "content_type": content_type, "size": size}

    async def probe_media(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        return await self._probe_resource(
            url,
            headers,
            allowed_content_types=MEDIA_CONTENT_TYPES,
            max_bytes=self.max_video_bytes,
            kind_label="视频",
        )

    async def probe_image(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        """Probe a public image while applying the same SSRF and redirect checks."""
        return await self._probe_resource(
            url,
            headers,
            allowed_content_types=IMAGE_CONTENT_TYPES,
            max_bytes=self.max_image_bytes,
            kind_label="图片",
        )

    async def _open_stream_httpx(
        self,
        url: str,
        request_headers: dict[str, str],
        *,
        media_kind: str,
    ) -> OpenedStream:
        current = url
        client = self._httpx_client()
        try:
            for redirect_count in range(self.max_redirects + 1):
                await self.validate_url(current)
                request = client.build_request("GET", current, headers=request_headers)
                response = await client.send(request, stream=True)
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    await response.aclose()
                    if not location or redirect_count >= self.max_redirects:
                        raise AppError("UPSTREAM_TIMEOUT", "上游重定向过多", retryable=True)
                    current = urljoin(current, location)
                    continue
                self._validate_stream_response(response.status_code, response.headers, media_kind=media_kind)

                async def close_httpx(open_response: httpx.Response = response) -> None:
                    await open_response.aclose()
                    await client.aclose()

                return OpenedStream(response=response, final_url=current, close_callback=close_httpx)
        except Exception:
            await client.aclose()
            raise
        await client.aclose()
        raise AppError("DOWNLOAD_FAILED", "无法打开上游媒体", retryable=True)

    @staticmethod
    def _validate_stream_response(
        status: int,
        headers: Mapping[str, str],
        *,
        media_kind: str = "video",
    ) -> None:
        if status not in {200, 206}:
            raise AppError("DOWNLOAD_FAILED", "上游媒体暂时不可下载", retryable=status >= 500)
        content_type = headers.get("content-type", "application/octet-stream").split(";", 1)[0]
        if media_kind == "image":
            valid_type = content_type in IMAGE_CONTENT_TYPES
            label = "图片"
        else:
            valid_type = content_type.startswith("video/") or content_type == "application/octet-stream"
            label = "视频"
        if not valid_type:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", f"上游返回了非{label}内容")

    async def _open_stream_aiohttp(
        self,
        url: str,
        request_headers: dict[str, str],
        *,
        media_kind: str,
    ) -> OpenedStream:
        current = url
        session = self._aiohttp_session()
        try:
            for redirect_count in range(self.max_redirects + 1):
                await self.validate_url(current)
                response = await session.get(current, headers=request_headers, allow_redirects=False)
                if response.status in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    response.release()
                    if not location or redirect_count >= self.max_redirects:
                        raise AppError("UPSTREAM_TIMEOUT", "上游重定向过多", retryable=True)
                    current = urljoin(current, location)
                    continue
                self._validate_stream_response(response.status, response.headers, media_kind=media_kind)
                adapter = AioHttpResponseAdapter(response)

                async def close_aiohttp(open_response: AioHttpResponseAdapter = adapter) -> None:
                    await open_response.aclose()
                    await session.close()

                return OpenedStream(response=adapter, final_url=current, close_callback=close_aiohttp)
        except (TimeoutError, aiohttp.ClientError) as error:
            await session.close()
            raise AppError("DOWNLOAD_FAILED", "上游媒体暂时不可下载", retryable=True) from error
        except Exception:
            await session.close()
            raise
        await session.close()
        raise AppError("DOWNLOAD_FAILED", "无法打开上游媒体", retryable=True)

    async def open_stream(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        range_header: str | None = None,
        media_kind: str = "video",
    ) -> OpenedStream:
        request_headers = dict(headers or {})
        if range_header:
            request_headers["Range"] = range_header
        if self.transport is not None:
            return await self._open_stream_httpx(url, request_headers, media_kind=media_kind)
        return await self._open_stream_aiohttp(url, request_headers, media_kind=media_kind)
