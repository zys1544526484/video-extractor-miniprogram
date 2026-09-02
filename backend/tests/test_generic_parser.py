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

