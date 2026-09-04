from __future__ import annotations

from app.config import Settings
from app.parsers.base import ParseContext
from app.parsers.generic import GenericParser


class FakeHttp:
    async def get_text(self, url: str):
        html = """
        <html><head>
          <title>Fixture title</title>
          <meta property="og:image" content="/cover.jpg">
          <script type="application/ld+json">{"contentUrl":"/media/video.mp4"}</script>
        </head><body><video><source src="/media/fallback.mp4"></video></body></html>
        """
        return "https://public.example/watch/1", html, {"content-type": "text/html"}

    async def probe_media(self, url: str):
        return {"url": url, "content_type": "video/mp4", "size": 1024}


class WebmHttp(FakeHttp):
    async def probe_media(self, url: str):
        return {"url": url, "content_type": "video/webm", "size": 2048}


class ImageHttp(FakeHttp):
    async def probe_media(self, url: str):
        return {"url": url, "content_type": "image/jpeg", "size": 512}


async def test_generic_parser_extracts_standard_html() -> None:
    parser = GenericParser()
    result = await parser.parse(
        "https://public.example/watch/1",
        ParseContext(settings=Settings(app_env="test"), http=FakeHttp()),
    )
    assert result.title == "Fixture title"
    assert result.cover_url == "https://public.example/cover.jpg"
    assert result.upstream_media_url == "https://public.example/media/fallback.mp4"
    assert result.mime_type == "video/mp4"


async def test_generic_parser_accepts_direct_mp4() -> None:
    result = await GenericParser().parse(
        "https://public.example/media/video.mp4",
        ParseContext(settings=Settings(app_env="test"), http=FakeHttp()),
    )
    assert result.upstream_media_url.endswith("video.mp4")


async def test_generic_parser_accepts_public_webm_for_later_mp4_conversion() -> None:
    result = await GenericParser().parse(
        "https://public.example/media/video.webm",
        ParseContext(settings=Settings(app_env="test"), http=WebmHttp()),
    )
    assert result.upstream_media_url.endswith("video.webm")
    assert result.mime_type == "video/webm"


async def test_generic_parser_supports_direct_public_image() -> None:
    result = await GenericParser().parse(
        "https://public.example/assets/photo.jpg",
        ParseContext(settings=Settings(app_env="test"), http=ImageHttp()),
    )
    assert result.media_type == "image"
    assert result.images[0].image_id == "image-1"
    assert result.upstream_media_url is None


async def test_generic_parser_does_not_turn_only_open_graph_cover_into_work_image() -> None:
    class CoverOnlyHttp(FakeHttp):
        async def get_text(self, url: str):
            return (
                "https://public.example/watch/cover",
                '<html><meta property="og:image" content="/cover.jpg"></html>',
                {"content-type": "text/html"},
            )

    try:
        await GenericParser().parse(
            "https://public.example/watch/cover",
            ParseContext(settings=Settings(app_env="test"), http=CoverOnlyHttp()),
        )
    except Exception as error:
        assert getattr(error, "code", None) == "PLATFORM_UNSUPPORTED"
    else:
        raise AssertionError("cover-only HTML must not produce a downloadable image")
