from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.security.tokens import decode_auth_token


def create_local_media(client: TestClient, auth_headers: dict[str, str]) -> tuple[str, int]:
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
            mime_type="video/mp4",
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


def test_range_and_tampered_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    token, _ = create_local_media(client, auth_headers)
    ranged = client.get(f"/api/v1/media/{token}/preview", headers={"Range": "bytes=0-9"})
    assert ranged.status_code == 206
    assert ranged.content == b"0123456789"

    missing = client.get(f"/api/v1/media/{token}x/preview")
    assert missing.status_code == 410
    assert missing.json()["error"]["code"] == "MEDIA_SESSION_EXPIRED"
