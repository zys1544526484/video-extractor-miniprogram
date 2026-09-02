from __future__ import annotations

import httpx
import pytest

from app.errors import AppError
from app.security.ssrf import is_public_ip, validate_public_url
from app.services.safe_http import PinnedPublicResolver, SafeHttpClient


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_private_addresses_are_not_public(address: str) -> None:
    assert is_public_ip(address) is False


@pytest.mark.asyncio
async def test_validate_rejects_localhost_and_private_dns() -> None:
    async def private_resolver(host: str) -> list[str]:
        return ["127.0.0.1"]

    with pytest.raises(AppError):
        await validate_public_url("http://localhost/a", private_resolver)
    with pytest.raises(AppError):
        await validate_public_url("https://example.com/a", private_resolver)


@pytest.mark.asyncio
async def test_redirect_is_revalidated_and_cannot_rebind() -> None:
    calls = 0

    async def rebinding_resolver(host: str) -> list[str]:
        nonlocal calls
        calls += 1
        return ["93.184.216.34"] if calls == 1 else ["127.0.0.1"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/second"})

    client = SafeHttpClient(
        timeout_seconds=2,
        max_redirects=2,
        max_video_bytes=1024,
        resolver=rebinding_resolver,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(AppError) as captured:
        await client.get_text("https://example.com/first")
    assert captured.value.code == "URL_INVALID"
    assert calls == 2


@pytest.mark.asyncio
async def test_redirect_to_metadata_ip_is_blocked() -> None:
    async def public_resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    client = SafeHttpClient(
        timeout_seconds=2,
        max_redirects=2,
        max_video_bytes=1024,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(AppError):
        await client.get_text("https://example.com/first")


@pytest.mark.asyncio
async def test_connector_resolver_pins_only_checked_public_addresses() -> None:
    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    records = await PinnedPublicResolver(resolver).resolve("example.com", 443)
    assert [record["host"] for record in records] == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_connector_resolver_rejects_rebound_private_address() -> None:
    async def rebound_resolver(host: str) -> list[str]:
        return ["127.0.0.1"]

    with pytest.raises(AppError) as captured:
        await PinnedPublicResolver(rebound_resolver).resolve("example.com", 443)
    assert captured.value.code == "URL_INVALID"
