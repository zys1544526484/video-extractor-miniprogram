from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        public_base_url="http://testserver",
        app_token_secret="test-token-secret-that-is-long-enough-123",
        mock_wechat_auth=True,
        download_access_mode="rewarded_ad",
        ad_attempt_min_seconds=0,
        temp_dir=tmp_path / "media",
        media_session_ttl_seconds=900,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/wechat", json={"code": "mock-login-code"})
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}
