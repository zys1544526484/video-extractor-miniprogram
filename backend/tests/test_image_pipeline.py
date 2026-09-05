from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.parsers.generic import GenericParser
from app.security.tokens import decode_auth_token
from app.services.parse_service import ParseService
from app.services.safe_http import SafeHttpClient


class GenericRegistry:
    def get(self, platform: str) -> GenericParser:
        return GenericParser()


def test_public_webpage_image_reaches_disk_preview_and_download(tmp_path) -> None:
    image_bytes = b"simulated-jpeg-content"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gallery":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=(
                    '<html><head><title>图片作品</title>'
                    '<meta property="og:image" content="/cover.jpg"></head>'
                    '<body><img src="/gallery-1.jpg"></body></html>'
                ).encode(),
            )
        if request.url.path == "/gallery-1.jpg":
            assert request.method == "GET"
            return httpx.Response(
                200,
                headers={
                    "content-type": "image/jpeg",
                    "content-length": str(len(image_bytes)),
                },
                content=image_bytes,
            )
        if request.url.path == "/single":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=(
                    '<html><head><title>单图作品</title>'
                    '<meta property="og:image" content="/photo.jpg"></head>'
                    '<body><img src="/photo.jpg"></body></html>'
                ).encode(),
            )
        if request.url.path == "/photo.jpg":
            if request.method == "HEAD":
                return httpx.Response(
                    200,
                    headers={
                        "content-type": "image/jpeg",
                        "content-length": str(len(image_bytes)),
                    },
                )
            return httpx.Response(
                200,
                headers={
                    "content-type": "image/jpeg",
                    "content-length": str(len(image_bytes)),
                },
                content=image_bytes,
            )
        if request.url.path == "/direct.jpg":
            if request.method == "HEAD":
                return httpx.Response(
                    200,
                    headers={
                        "content-type": "image/jpeg",
                        "content-length": str(len(image_bytes)),
                    },
                )
            return httpx.Response(
                200,
                headers={
                    "content-type": "image/jpeg",
                    "content-length": str(len(image_bytes)),
                },
                content=image_bytes,
            )
        return httpx.Response(404)

    settings = Settings(
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'image.db'}",
        public_base_url="http://testserver",
        app_token_secret="image-pipeline-test-secret-1234567890",
        mock_wechat_auth=True,
        download_access_mode="free",
        temp_dir=tmp_path / "media",
        min_free_disk_bytes=0,
    )
    with TestClient(create_app(settings)) as client:
        login = client.post("/api/v1/auth/wechat", json={"code": "image-pipeline"})
        token = login.json()["token"]
        user_id = decode_auth_token(token, settings.app_token_secret.get_secret_value())
        safe_http = SafeHttpClient(
            timeout_seconds=1,
            max_redirects=2,
            max_video_bytes=settings.max_source_video_bytes,
            resolver=lambda host: asyncio.sleep(0, result=["93.184.216.34"]),
            transport=httpx.MockTransport(handler),
        )
        service = ParseService(
            settings,
            safe_http,
            GenericRegistry(),
            client.app.state.media_sessions,
        )
        client.app.state.safe_http = safe_http

        direct = asyncio.run(service.parse("https://example.com/direct.jpg", user_id))
        assert direct.media_type == "image"
        assert direct.images

        single = asyncio.run(service.parse("https://example.com/single", user_id))
        assert single.media_type == "image"
        assert [image["alt"] for image in single.images] == ["单图作品"]
        assert single.images[0]["mime_type"] == "image/jpeg"

        result = asyncio.run(service.parse("https://example.com/gallery", user_id))
        assert result.media_type == "image"
        assert len(result.images) == 1
        assert result.images[0]["size_bytes"] == len(image_bytes)
        assert result.images[0]["session_id"]
        assert result.images[0]["mime_type"] == "image/jpeg"
        assert result.images[0]["alt"] == "图片作品"

        preview_path = urlsplit(
            f"http://testserver/api/v1/media/{result.session_id}/preview"
        ).path
        # The public result exposes capability URLs; use the actual token URL
        # returned by the parser result for the HTTP route checks below.
        preview_path = urlsplit(result.preview_url).path
        download_path = urlsplit(result.download_url).path
        preview = client.get(preview_path)
        downloaded = client.get(download_path)
        assert preview.status_code == 200
        assert downloaded.status_code == 200
        assert preview.content == image_bytes
        assert downloaded.content == image_bytes
        assert preview.headers["content-type"].startswith("image/jpeg")
        assert downloaded.headers["content-disposition"].endswith(".jpg\"")
