from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import configure_logging, create_app
from app.models import User


def test_health_has_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == "ok"
    assert payload["request_id"].startswith("req_")
    assert response.headers["x-request-id"] == payload["request_id"]


def test_auth_and_download_entitlement_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    initial = client.get("/api/v1/entitlement", headers=auth_headers)
    assert initial.status_code == 200
    assert initial.json()["entitled"] is False
    assert initial.json()["access_mode"] == "rewarded_ad"
    assert initial.json()["can_download"] is False

    attempt = client.post("/api/v1/entitlement/ad-attempt", headers=auth_headers, json={})
    assert attempt.status_code == 200
    attempt_token = attempt.json()["attempt_token"]

    unlocked = client.post(
        "/api/v1/entitlement/ad-complete",
        headers={**auth_headers, "Idempotency-Key": "ad_event_00000001"},
        json={"attempt_token": attempt_token},
    )
    assert unlocked.status_code == 200
    first_until = unlocked.json()["unlock_until"]
    assert unlocked.json()["entitled"] is True

    duplicate = client.post(
        "/api/v1/entitlement/ad-complete",
        headers={**auth_headers, "Idempotency-Key": "ad_event_00000002"},
        json={"attempt_token": attempt_token},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["unlock_until"] == first_until


def test_ad_complete_requires_idempotency_key(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/entitlement/ad-complete",
        headers=auth_headers,
        json={"attempt_token": "x" * 43},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "URL_INVALID"


def test_ad_complete_rejects_unissued_attempt(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/entitlement/ad-complete",
        headers={**auth_headers, "Idempotency-Key": "ad_event_unissued_1"},
        json={"attempt_token": "x" * 43},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AD_CONFIRM_INVALID"


def test_consumed_ad_attempt_cannot_unlock_again_after_entitlement_expires(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    attempt = client.post("/api/v1/entitlement/ad-attempt", headers=auth_headers, json={})
    attempt_token = attempt.json()["attempt_token"]
    first = client.post(
        "/api/v1/entitlement/ad-complete",
        headers={**auth_headers, "Idempotency-Key": "ad_event_first_use"},
        json={"attempt_token": attempt_token},
    )
    assert first.status_code == 200

    database = client.app.state.database
    with database.session_factory() as session:
        user = session.scalar(select(User))
        assert user is not None
        user.unlock_until = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        session.commit()

    replay = client.post(
        "/api/v1/entitlement/ad-complete",
        headers={**auth_headers, "Idempotency-Key": "ad_event_replayed"},
        json={"attempt_token": attempt_token},
    )
    assert replay.status_code == 403
    assert replay.json()["error"]["code"] == "AD_CONFIRM_INVALID"


def test_parse_is_authenticated_but_not_entitlement_gated(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "parse_no_url_0001"},
        json={"text": "没有链接"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "URL_NOT_FOUND"


def test_parse_rejects_unknown_quality(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/parse",
        headers=auth_headers,
        json={"text": "https://example.com/video", "quality": "4k"},
    )

    assert response.status_code == 422


def test_auth_errors_do_not_leak_traceback(client: TestClient) -> None:
    response = client.get("/api/v1/entitlement", headers={"Authorization": "Bearer tampered"})
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "AUTH_REQUIRED"
    assert "traceback" not in response.text.lower()


def test_http_client_info_logging_is_disabled_for_wechat_secrets() -> None:
    configure_logging("INFO")
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_media_access_token_is_not_written_to_application_logs(client: TestClient, caplog) -> None:
    token = "capability-token-for-log-test"
    with caplog.at_level(logging.INFO, logger="video_extractor"):
        response = client.get(f"/api/v1/media/{token}/preview")

    assert response.status_code == 410
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in messages
    assert "/api/v1/media/<token>/preview" in messages


def test_production_requires_alembic_head_before_startup(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'unmigrated.db'}",
        public_base_url="https://media-api.valid-domain.cn",
        app_token_secret="vF3_7sQ9-jL2_xM8-aC4_kR6-zT1_wN5",
        wechat_app_id="wx1234567890abcdef",
        wechat_app_secret="0123456789abcdef0123456789abcdef",
        mock_wechat_auth=False,
        dev_bypass_download_entitlement=False,
        download_access_mode="free",
        temp_dir=tmp_path / "media",
    )
    with pytest.raises(RuntimeError, match="Alembic"):
        with TestClient(create_app(settings)):
            pass


def test_development_can_bypass_download_entitlement_without_ad(tmp_path) -> None:
    settings = Settings(
        app_env="development",
        database_url=f"sqlite:///{tmp_path / 'development.db'}",
        public_base_url="http://testserver",
        app_token_secret="development-test-secret-that-is-long-enough",
        mock_wechat_auth=True,
        dev_bypass_download_entitlement=True,
        download_access_mode="rewarded_ad",
        temp_dir=tmp_path / "media",
    )
    with TestClient(create_app(settings)) as development_client:
        auth = development_client.post("/api/v1/auth/wechat", json={"code": "local-developer"})
        token = auth.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        entitlement = development_client.get("/api/v1/entitlement", headers=headers)
        attempt = development_client.post("/api/v1/entitlement/ad-attempt", headers=headers, json={})

    assert entitlement.status_code == 200
    assert entitlement.json()["entitled"] is True
    assert entitlement.json()["development_bypass"] is True
    assert attempt.status_code == 200
    assert attempt.json()["attempt_required"] is False
    assert attempt.json()["attempt_token"] is None


def test_free_mode_allows_download_and_disables_ad_endpoints(tmp_path) -> None:
    settings = Settings(
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'free.db'}",
        public_base_url="http://testserver",
        app_token_secret="free-mode-test-secret-that-is-long-enough",
        mock_wechat_auth=True,
        download_access_mode="free",
        temp_dir=tmp_path / "media",
    )
    with TestClient(create_app(settings)) as free_client:
        auth = free_client.post("/api/v1/auth/wechat", json={"code": "free-user"})
        headers = {"Authorization": f"Bearer {auth.json()['token']}"}
        access = free_client.get("/api/v1/entitlement", headers=headers)
        attempt = free_client.post("/api/v1/entitlement/ad-attempt", headers=headers, json={})
        complete = free_client.post(
            "/api/v1/entitlement/ad-complete",
            headers={**headers, "Idempotency-Key": "free_mode_attempt"},
            json={"attempt_token": "x" * 43},
        )

    assert access.status_code == 200
    assert access.json()["access_mode"] == "free"
    assert access.json()["can_download"] is True
    assert access.json()["unlock_until"] is None
    assert attempt.status_code == 409
    assert attempt.json()["error"]["code"] == "FEATURE_DISABLED"
    assert complete.status_code == 409
    assert complete.json()["error"]["code"] == "FEATURE_DISABLED"
