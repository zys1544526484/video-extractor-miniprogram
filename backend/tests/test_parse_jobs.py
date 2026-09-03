from __future__ import annotations

import asyncio
import time
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import MediaAccessToken, ParseJob
from app.schemas import ParsePublicResult
from app.security.tokens import decode_auth_token
from app.services.parse_jobs import utc_now_naive


class SuccessfulParseService:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    async def parse(self, text, user_id, quality, progress=None) -> ParsePublicResult:
        if progress:
            await progress(25, "解析页面")
        directory = self.client.app.state.settings.temp_dir / f"job-{user_id}"
        directory.mkdir(parents=True, exist_ok=True)
        file = directory / "video.mp4"
        file.write_bytes(b"test-video")
        media = await self.client.app.state.media_sessions.create(
            user_id=user_id,
            platform="测试平台",
            title="持久任务",
            upstream_url=None,
            temporary_file=str(file),
            required_headers={},
            mime_type="video/mp4",
            size_bytes=file.stat().st_size,
        )
        if progress:
            await progress(95, "生成下载链接")
        return ParsePublicResult(
            session_id=media.session_id,
            platform="测试平台",
            title="持久任务",
            cover_url="",
            duration_seconds=1,
            size_bytes=file.stat().st_size,
            quality_label="测试画质",
            requested_quality=quality,
            preview_url="unused",
            download_url="unused",
            expires_at=media.expires_at,
            watermark_status="unknown",
            notice="",
        )


class SlowParseService:
    async def parse(self, text, user_id, quality, progress=None) -> ParsePublicResult:
        if progress:
            await progress(10, "等待取消")
        await asyncio.sleep(30)
        raise AssertionError("cancelled task must not complete")


def wait_for_status(
    client: TestClient,
    job_id: str,
    headers: dict[str, str],
    statuses: set[str],
) -> dict:
    deadline = time.time() + 3
    while time.time() < deadline:
        response = client.get(f"/api/v1/parse/jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        job = response.json()["job"]
        if job["status"] in statuses:
            return job
        if job["status"] in {"failed", "cancelled", "expired"}:
            raise AssertionError(f"job reached unexpected terminal state: {job}")
        time.sleep(0.02)
    raise AssertionError(f"job did not reach {statuses}; last state: {job}")


def test_parse_job_is_idempotent_persistent_and_user_bound(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client.app.state.parse_jobs.parse_service = SuccessfulParseService(client)
    headers = {**auth_headers, "Idempotency-Key": "parse_job_test_0001"}
    created = client.post(
        "/api/v1/parse",
        headers=headers,
        json={"text": "https://example.com/video", "quality": "720p"},
    )
    assert created.status_code == 202
    job_id = created.json()["job"]["job_id"]

    ready = wait_for_status(client, job_id, auth_headers, {"ready"})
    assert ready["progress"] == 100
    assert ready["result"]["requested_quality"] == "720p"
    assert ready["result"]["preview_url"].endswith("/preview")

    repeated = client.post(
        "/api/v1/parse",
        headers=headers,
        json={"text": "https://example.com/video", "quality": "720p"},
    )
    assert repeated.status_code == 202
    assert repeated.json()["job"]["job_id"] == job_id

    raw_token = ready["result"]["preview_url"].split("/media/", 1)[1].split("/", 1)[0]
    with client.app.state.database.session_factory() as session:
        hashes = list(session.scalars(select(MediaAccessToken.token_hash)))
    assert raw_token not in hashes

    second_auth = client.post("/api/v1/auth/wechat", json={"code": "different-user"}).json()["token"]
    forbidden = client.get(
        f"/api/v1/parse/jobs/{job_id}",
        headers={"Authorization": f"Bearer {second_auth}"},
    )
    assert forbidden.status_code == 404


def test_processing_job_can_be_cancelled(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client.app.state.parse_jobs.parse_service = SlowParseService()
    created = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "parse_job_cancel_01"},
        json={"text": "https://example.com/slow", "quality": "original"},
    )
    job_id = created.json()["job"]["job_id"]
    wait_for_status(client, job_id, auth_headers, {"processing"})

    cancelled = client.delete(f"/api/v1/parse/jobs/{job_id}", headers=auth_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"


def test_parse_requires_idempotency_key(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/parse",
        headers=auth_headers,
        json={"text": "https://example.com/video"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_INVALID"


def test_processing_job_is_requeued_after_service_restart(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    service = client.app.state.parse_jobs
    client.portal.call(service.stop)
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    settings = client.app.state.settings
    user_id = decode_auth_token(token, settings.app_token_secret.get_secret_value())
    now = utc_now_naive()
    job_id = "pj_restart_recovery_test"
    with client.app.state.database.session_factory() as session:
        session.add(
            ParseJob(
                job_id=job_id,
                user_id=user_id,
                idempotency_hash="a" * 64,
                source_url="https://example.com/recovered",
                platform="generic",
                requested_quality="540p",
                status="processing",
                progress=60,
                stage="服务中断前正在处理",
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(minutes=10),
            )
        )
        session.commit()

    service.parse_service = SuccessfulParseService(client)
    client.portal.call(service.start)

    ready = wait_for_status(client, job_id, auth_headers, {"ready"})
    assert ready["progress"] == 100
    assert ready["result"]["requested_quality"] == "540p"
