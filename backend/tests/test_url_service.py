from __future__ import annotations

import pytest

from app.errors import AppError
from app.services.url_service import detect_platform, extract_first_http_url


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://example.com/a?x=1", "https://example.com/a?x=1"),
        ("复制这段 https://v.douyin.com/abc/，打开看看", "https://v.douyin.com/abc/"),
        ("先 https://a.example/v.mp4 后 https://b.example/v.mp4", "https://a.example/v.mp4"),
        ("\n https://www.bilibili.com/video/BV1xx 】", "https://www.bilibili.com/video/BV1xx"),
    ],
)
def test_extract_first_url(text: str, expected: str) -> None:
    assert extract_first_http_url(text) == expected


@pytest.mark.parametrize("text", ["no url", "javascript:alert(1)", "file:///tmp/a.mp4", "ftp://a/b"])
def test_reject_non_http_input(text: str) -> None:
    with pytest.raises(AppError) as captured:
        extract_first_http_url(text)
    assert captured.value.code == "URL_NOT_FOUND"


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://b23.tv/abc", "bilibili"),
        ("https://www.bilibili.com/video/a", "bilibili"),
        ("https://weibo.com/tv/show/a", "weibo"),
        ("https://www.xiaohongshu.com/explore/a", "xiaohongshu"),
        ("https://v.douyin.com/a", "douyin"),
        ("https://v.kuaishou.com/a", "kuaishou"),
        ("https://douyin.com.attacker.example/a", "generic"),
        ("https://fakebilibili.com/a", "generic"),
    ],
)
def test_platform_detection_uses_domain_boundaries(url: str, platform: str) -> None:
    assert detect_platform(url) == platform

