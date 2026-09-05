from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.security.tokens import decode_auth_token
from app.services.media_sessions import MediaSessionStore


def create_local_media(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    mime_type: str = "video/mp4",
) -> tuple[str, int]:
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    settings = client.app.state.settings
    user_id = decode_auth_token(token, settings.app_token_secret.get_secret_value())
    directory = settings.temp_dir / "test-session"
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "video.mp4"
    file.write_bytes(b"0123456789" * 100)
    media = asyncio.run(
        client.app.state.media_sessions.create(
            user_id=user_id,
            platform="测试平台",
            title="标题\r\nContent-Disposition: bad",
            upstream_url=None,
            temporary_file=str(file),
            required_headers={},
            mime_type=mime_type,
            size_bytes=file.stat().st_size,
        )
    )
    return media.token, user_id


def test_preview_is_capability_url_but_download_needs_entitlement(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    token, _ = create_local_media(client, auth_headers)
    preview = client.get(f"/api/v1/media/{token}/preview")
    assert preview.status_code == 200
    assert preview.content.startswith(b"0123456789")

    blocked = client.get(f"/api/v1/media/{token}/download", headers=auth_headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ENTITLEMENT_REQUIRED"

    attempt = client.post("/api/v1/entitlement/ad-attempt", headers=auth_headers, json={})
    attempt_token = attempt.json()["attempt_token"]
    client.post(
        "/api/v1/entitlement/ad-complete",
        headers={**auth_headers, "Idempotency-Key": "ad_event_download_1"},
        json={"attempt_token": attempt_token},
    )
    downloaded = client.get(f"/api/v1/media/{token}/download", headers=auth_headers)
    assert downloaded.status_code == 200
    disposition = downloaded.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert "attachment" in disposition

    copied_link = client.get(f"/api/v1/media/{token}/download")
    assert copied_link.status_code == 200
    assert copied_link.content == downloaded.content


def test_range_and_tampered_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    token, _ = create_local_media(client, auth_headers)
    ranged = client.get(f"/api/v1/media/{token}/preview", headers={"Range": "bytes=0-9"})
    assert ranged.status_code == 206
    assert ranged.content == b"0123456789"

    missing = client.get(f"/api/v1/media/{token}x/preview")
    assert missing.status_code == 410
    assert missing.json()["error"]["code"] == "MEDIA_SESSION_EXPIRED"


def test_free_mode_download_link_is_independent_of_authorization(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.app.state.settings.download_access_mode = "free"
    token, _ = create_local_media(client, auth_headers, mime_type="video/*")

    unauthenticated = client.get(f"/api/v1/media/{token}/download")
    downloaded = client.get(f"/api/v1/media/{token}/download", headers=auth_headers)

    # A copied capability URL must work when opened outside the mini program;
    # the short-lived random token still binds it to a server media session.
    assert unauthenticated.status_code == 200
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"0123456789")
    assert downloaded.headers["content-type"].startswith("video/mp4")
    assert ".mp4" in downloaded.headers["content-disposition"]


def test_media_token_survives_store_restart(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    token, user_id = create_local_media(client, auth_headers)
    settings = client.app.state.settings
    restarted_store = MediaSessionStore(
        client.app.state.database,
        settings.media_session_ttl_seconds,
        settings.temp_dir,
        settings.temp_file_ttl_seconds,
    )

    restored = asyncio.run(restarted_store.get(token))

    assert restored.user_id == user_id
    assert restored.temporary_file.read_bytes().startswith(b"0123456789")


def test_image_media_uses_image_content_type_and_filename(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    user_id = decode_auth_token(token, client.app.state.settings.app_token_secret.get_secret_value())
    directory = client.app.state.settings.temp_dir / "image-session"
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "cover.jpg"
    file.write_bytes(b"fake-jpeg")
    media = asyncio.run(
        client.app.state.media_sessions.create(
            user_id=user_id,
            platform="测试平台",
            title="封面",
            upstream_url=None,
            temporary_file=str(file),
            required_headers={},
            mime_type="image/jpeg",
            size_bytes=file.stat().st_size,
        )
    )
    client.app.state.settings.download_access_mode = "free"
    response = client.get(f"/api/v1/media/{media.token}/download", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.headers["content-disposition"].endswith(".jpg\"")


def test_remote_media_session_keeps_validated_source_for_on_demand_streaming(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    user_id = decode_auth_token(token, client.app.state.settings.app_token_secret.get_secret_value())
    media = asyncio.run(
        client.app.state.media_sessions.create(
            user_id=user_id,
            platform="测试平台",
            title="远程视频",
            upstream_url="https://cdn.example/video.mp4",
            temporary_file=None,
            required_headers={
                "Referer": "https://example.com/watch",
                "X-Unsafe": "discarded",
            },
            mime_type="video/mp4",
            size_bytes=123,
        )
    )

    restored = asyncio.run(client.app.state.media_sessions.get(media.token))
    assert restored.temporary_file is None
    assert restored.upstream_url == "https://cdn.example/video.mp4"
    assert restored.required_headers == {"Referer": "https://example.com/watch"}
