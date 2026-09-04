from __future__ import annotations

import json
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..errors import AppError
from ..schemas import ParserImageModel, ParserResultModel
from .base import BaseParser, ParseContext

DIRECT_VIDEO_EXTENSIONS = {".m4v", ".mkv", ".mov", ".mp4", ".webm"}
DIRECT_IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}


class GenericParser(BaseParser):
    platform = "generic"

    def can_handle(self, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    async def _media_result(
        self,
        media_url: str,
        canonical_url: str,
        context: ParseContext,
        *,
        title: str = "公开网页视频",
        cover_url: str = "",
        images: list[ParserImageModel] | None = None,
    ) -> ParserResultModel:
        metadata = await context.http.probe_media(media_url)
        return ParserResultModel(
            platform="generic",
            canonical_url=canonical_url,
            title=title[:200] or "公开网页视频",
            cover_url=cover_url,
            upstream_media_url=metadata["url"],
            mime_type=metadata["content_type"],
            size_bytes=metadata["size"],
            quality_label="公开资源",
            watermark_status="unknown",
            notices=["普通网页视频来源可能随页面变化而失效；非 MP4 源将自动转换"],
            images=images or [],
        )

    async def _image_result(
        self,
        media_url: str,
        canonical_url: str,
        context: ParseContext,
        *,
        title: str = "公开网页图片",
        image_id: str = "image-1",
    ) -> ParserResultModel:
        metadata = await context.http.probe_media(media_url)
        content_type = str(metadata.get("content_type") or "image/jpeg").split(";", 1)[0].lower()
        if content_type == "image/jpg":
            content_type = "image/jpeg"
        if not content_type.startswith("image/"):
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", "公开资源不是标准图片")
        return ParserResultModel(
            platform="generic",
            canonical_url=canonical_url,
            title=title[:200] or "公开网页图片",
            media_type="image",
            mime_type=content_type,
            size_bytes=metadata.get("size"),
            quality_label=None,
            watermark_status="unknown",
            images=[
                ParserImageModel(
                    image_id=image_id,
                    url=metadata["url"],
                    mime_type=content_type,
                    size_bytes=metadata.get("size"),
                    alt=title[:200],
                )
            ],
            notices=["公开网页图片来源可能随页面变化而失效"],
        )

    async def parse(self, url: str, context: ParseContext) -> ParserResultModel:
        suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
        if suffix in DIRECT_VIDEO_EXTENSIONS:
            return await self._media_result(url, url, context)
        if suffix in DIRECT_IMAGE_EXTENSIONS:
            return await self._image_result(url, url, context)

        final_url, html, _ = await context.http.get_text(url)
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        title_meta = soup.find("meta", attrs={"property": "og:title"})
        if title_meta and title_meta.get("content"):
            title = str(title_meta["content"])
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()

        cover = ""
        cover_meta = soup.find("meta", attrs={"property": "og:image"})
        if cover_meta and cover_meta.get("content"):
            cover = urljoin(final_url, str(cover_meta["content"]))

        candidates: list[str] = []
        image_candidates: list[str] = []
        for element in soup.select("img[src], picture source[src]"):
            source = element.get("src")
            if source:
                image_candidates.append(urljoin(final_url, str(source)))
        for element in soup.select("video[src], video source[src], source[src]"):
            if element.get("src"):
                candidates.append(urljoin(final_url, str(element["src"])))
        for prop in ("og:video", "og:video:url", "og:video:secure_url", "twitter:player:stream"):
            element = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            if element and element.get("content"):
                candidates.append(urljoin(final_url, str(element["content"])))
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "null")
            except (TypeError, json.JSONDecodeError):
                continue
            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if isinstance(node, dict):
                    for key in ("contentUrl", "embedUrl"):
                        if isinstance(node.get(key), str):
                            candidates.append(urljoin(final_url, node[key]))
                    image_value = node.get("image")
                    if isinstance(image_value, str):
                        image_candidates.append(urljoin(final_url, image_value))
                    elif isinstance(image_value, list):
                        image_candidates.extend(
                            urljoin(final_url, value)
                            for value in image_value
                            if isinstance(value, str)
                        )

        errors: list[AppError] = []
        unique_images = [
            candidate
            for candidate in dict.fromkeys(image_candidates)
            if candidate != cover
        ][:8]
        work_images = [
            ParserImageModel(
                image_id=f"image-{index}",
                url=image_url,
                alt=title[:200] or f"公开图片 {index}",
            )
            for index, image_url in enumerate(unique_images, start=1)
        ]
        for candidate in dict.fromkeys(candidates):
            try:
                return await self._media_result(
                    candidate,
                    final_url,
                    context,
                    title=title,
                    cover_url=cover,
                    images=work_images,
                )
            except AppError as error:
                errors.append(error)
        if errors and any(error.code == "MEDIA_TOO_LARGE" for error in errors):
            raise AppError("MEDIA_TOO_LARGE", "页面中的源视频超过服务器可处理上限")
        # Only explicit image elements/JSON-LD images are work images.  The
        # OpenGraph cover is deliberately excluded, so a video cover can never
        # be presented as a downloadable work image.
        if unique_images:
            return ParserResultModel(
                platform="generic",
                canonical_url=final_url,
                title=title[:200] or "公开网页图片",
                media_type="image",
                watermark_status="unknown",
                images=work_images,
                share_text=f"{title or '公开网页图片'}\n{final_url}",
                notices=["仅展示页面明确提供的图片，不会把视频封面当作作品图片"],
            )
        raise AppError("PLATFORM_UNSUPPORTED", "该公开网页中未找到标准视频资源")
