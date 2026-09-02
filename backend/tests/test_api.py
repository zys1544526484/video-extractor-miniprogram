from __future__ import annotations

from fastapi.testclient import TestClient


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

    unlocked = client.post(
        "/api/v1/entitlement/ad-complete",
        headers={**auth_headers, "Idempotency-Key": "ad_event_00000001"},
        json={},
    )
    assert unlocked.status_code == 200
    first_until = unlocked.json()["unlock_until"]
    assert unlocked.json()["entitled"] is True

    duplicate = client.post(
        "/api/v1/entitlement/ad-complete",
        headers={**auth_headers, "Idempotency-Key": "ad_event_00000002"},
        json={},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["unlock_until"] == first_until


def test_ad_complete_requires_idempotency_key(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/entitlement/ad-complete", headers=auth_headers, json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "URL_INVALID"


def test_parse_is_authenticated_but_not_entitlement_gated(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/api/v1/parse", headers=auth_headers, json={"text": "没有链接"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "URL_NOT_FOUND"


def test_auth_errors_do_not_leak_traceback(client: TestClient) -> None:
    response = client.get("/api/v1/entitlement", headers={"Authorization": "Bearer tampered"})
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "AUTH_REQUIRED"
    assert "traceback" not in response.text.lower()

