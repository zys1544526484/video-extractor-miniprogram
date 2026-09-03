from __future__ import annotations

import socket

import pytest

from app.errors import AppError
from app.parsers import yt_dlp_worker
from app.parsers.yt_dlp_adapter import YtDlpAdapter, reject_live_streams


def _dns_results(*addresses: str) -> list[tuple[object, ...]]:
    return [
        (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in addresses
    ]


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.0.0.8",),
        ("169.254.169.254",),
        ("::1",),
        ("fc00::1",),
        ("93.184.216.34", "127.0.0.1"),
    ],
)
def test_guarded_dns_rejects_non_public_targets(monkeypatch, addresses: tuple[str, ...]) -> None:
    monkeypatch.setattr(
        yt_dlp_worker,
        "_ORIGINAL_GETADDRINFO",
        lambda *args, **kwargs: _dns_results(*addresses),
    )

    with pytest.raises(OSError, match="not a public IP"):
        yt_dlp_worker.guarded_getaddrinfo("media.example", 443)


def test_guarded_dns_allows_public_targets(monkeypatch) -> None:
    expected = _dns_results("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946")
    monkeypatch.setattr(yt_dlp_worker, "_ORIGINAL_GETADDRINFO", lambda *args, **kwargs: expected)

    assert yt_dlp_worker.guarded_getaddrinfo("media.example", 443) == expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/video.mp4",
        "https://user:password@example.com/video",
        "//example.com/video",
        "not-a-url",
    ],
)
def test_worker_rejects_invalid_initial_urls(url: str) -> None:
    with pytest.raises(AppError, match="链接格式无效"):
        yt_dlp_worker.validate_initial_url(url)


def test_live_streams_are_rejected_before_media_download() -> None:
    assert reject_live_streams({"is_live": True}, incomplete=False)
    assert reject_live_streams({"is_live": False}, incomplete=False) is None


def test_client_codec_filter_accepts_h264_and_hevc_but_not_av1() -> None:
    assert YtDlpAdapter._compatible_video_codec({"vcodec": "avc1.64001f"}) == ("H.264", 2)
    assert YtDlpAdapter._compatible_video_codec({"vcodec": "hev1.1.6.L120.90"}) == (
        "H.265",
        1,
    )
    assert YtDlpAdapter._compatible_video_codec({"vcodec": "av01.0.08M.08"}) is None


def test_bilibili_selector_uses_best_size_bounded_h264_pair() -> None:
    info = {
        "formats": [
            {
                "format_id": "30080",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.640032",
                "acodec": "none",
                "height": 1080,
                "filesize": 396_224_122,
            },
            {
                "format_id": "30064",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.64001F",
                "acodec": "none",
                "height": 720,
                "filesize": 187_315_924,
            },
            {
                "format_id": "30032",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.64001E",
                "acodec": "none",
                "height": 480,
                "filesize": 106_037_229,
            },
            {
                "format_id": "30280",
                "protocol": "https",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 132,
                "filesize": 64_129_775,
            },
            {
                "format_id": "30232",
                "protocol": "https",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 69,
                "filesize": 34_936_385,
            },
        ]
    }

    selected, quality, estimated_size = YtDlpAdapter._select_bilibili_download_format(
        info,
        180 * 1024 * 1024,
    )

    assert selected == "30032+30232"
    assert quality == "480P H.264"
    assert estimated_size == 140_973_614

    selected_540, quality_540, estimated_540 = (
        YtDlpAdapter._select_bilibili_download_format(
            info,
            180 * 1024 * 1024,
            "540p",
        )
    )
    assert selected_540 == "30032+30232"
    assert quality_540 == "480P H.264（540P 档）"
    assert estimated_540 == 140_973_614


def test_bilibili_selector_does_not_silently_downgrade_original_quality() -> None:
    info = {
        "formats": [
            {
                "format_id": "1080",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.640032",
                "acodec": "none",
                "height": 1080,
                "filesize": 360 * 1024 * 1024,
            },
            {
                "format_id": "720",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.64001F",
                "acodec": "none",
                "height": 720,
                "filesize": 175 * 1024 * 1024,
            },
            {
                "format_id": "720-hevc",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "hev1.1.6.L120.90",
                "acodec": "none",
                "height": 720,
                "filesize": 100 * 1024 * 1024,
            },
            {
                "format_id": "480",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.64001E",
                "acodec": "none",
                "height": 480,
                "filesize": 80 * 1024 * 1024,
            },
            {
                "format_id": "audio",
                "protocol": "https",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "filesize": 20 * 1024 * 1024,
            },
        ]
    }

    with pytest.raises(AppError) as caught:
        YtDlpAdapter._select_bilibili_download_format(
            info,
            180 * 1024 * 1024,
            "original",
        )

    assert caught.value.code == "MEDIA_TOO_LARGE"
    assert "改选较低画质" in caught.value.message

    selected_720, quality_720, estimated_720 = (
        YtDlpAdapter._select_bilibili_download_format(
            info,
            180 * 1024 * 1024,
            "720p",
        )
    )
    assert selected_720 == "720-hevc+audio"
    assert quality_720 == "720P H.265"
    assert estimated_720 == 120 * 1024 * 1024

    selected_large, quality_large, _ = YtDlpAdapter._select_bilibili_download_format(
        info,
        2 * 1024 * 1024 * 1024,
        "original",
    )
    assert selected_large == "1080+audio"
    assert quality_large == "1080P H.264 · 原视频"


def test_bilibili_selector_rejects_when_compatible_pair_is_too_large() -> None:
    info = {
        "formats": [
            {
                "format_id": "video",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.640032",
                "acodec": "none",
                "height": 1080,
                "filesize": 170 * 1024 * 1024,
            },
            {
                "format_id": "audio",
                "protocol": "https",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "filesize": 20 * 1024 * 1024,
            },
        ]
    }

    with pytest.raises(AppError) as caught:
        YtDlpAdapter._select_bilibili_download_format(info, 180 * 1024 * 1024)

    assert caught.value.code == "MEDIA_TOO_LARGE"


@pytest.mark.asyncio
async def test_adapter_worker_blocks_loopback_without_connecting(settings) -> None:
    settings.parse_timeout_seconds = 5
    adapter = YtDlpAdapter(settings)

    with pytest.raises(AppError) as caught:
        await adapter.extract("http://127.0.0.1/video", "weibo")

    assert caught.value.code == "PLATFORM_CHANGED"
