from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import MediaAccessToken, MediaSessionRecord, ParseJob
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
            expires_at=media.access_token_expires_at,
            media_expires_at=media.expires_at,
            watermark_status="unknown",
            notice="",
        )


class SlowParseService:
    async def parse(self, text, user_id, quality, progress=None) -> ParsePublicResult:
        if progress:
            await progress(10, "等待取消")
        await asyncio.sleep(30)
        raise AssertionError("cancelled task must not complete")


class ConcurrentParseService:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.release = asyncio.Event()
        self.started = 0
        self.active = 0
        self.max_active = 0

    async def parse(self, text, user_id, quality, progress=None) -> ParsePublicResult:
        self.started += 1
        sequence = self.started
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if progress:
                await progress(20, "并发测试")
            await self.release.wait()
            directory = self.client.app.state.settings.temp_dir / f"concurrent-{sequence}"
            directory.mkdir(parents=True, exist_ok=True)
            file = directory / "video.mp4"
            file.write_bytes(f"video-{sequence}".encode())
            media = await self.client.app.state.media_sessions.create(
                user_id=user_id,
                platform="测试平台",
                title=f"并发任务 {sequence}",
                upstream_url=None,
                temporary_file=str(file),
                required_headers={},
                mime_type="video/mp4",
                size_bytes=file.stat().st_size,
            )
            return ParsePublicResult(
                session_id=media.session_id,
                platform="测试平台",
                title=f"并发任务 {sequence}",
                cover_url="",
                duration_seconds=1,
                size_bytes=file.stat().st_size,
                quality_label="测试画质",
                requested_quality=quality,
                preview_url="unused",
                download_url="unused",
                expires_at=media.access_token_expires_at,
                media_expires_at=media.expires_at,
                watermark_status="unknown",
                notice="",
            )
        finally:
            self.active -= 1


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


def test_ready_job_reissues_expired_token_without_extending_media_session(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client.app.state.parse_jobs.parse_service = SuccessfulParseService(client)
    client.app.state.media_sessions.ttl_seconds = 24 * 60 * 60
    created = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "parse_token_refresh_e2e_01"},
        json={"text": "https://example.com/token-refresh", "quality": "original"},
    )
    job_id = created.json()["job"]["job_id"]
    first = wait_for_status(client, job_id, auth_headers, {"ready"})["result"]
    now = utc_now_naive()
    first_expires = first["expires_at"]
    media_expires = first["media_expires_at"]
    first_token = first["preview_url"].split("/media/", 1)[1].split("/", 1)[0]
    first_ttl = (
        datetime.fromisoformat(first_expires.replace("Z", "+00:00"))
        - now.replace(tzinfo=UTC)
    ).total_seconds()
    assert 890 <= first_ttl <= 910
    media_retention_ttl = (
        datetime.fromisoformat(media_expires.replace("Z", "+00:00"))
        - now.replace(tzinfo=UTC)
    ).total_seconds()
    assert media_retention_ttl > 12 * 60 * 60

    with client.app.state.database.session_factory() as session:
        access = session.get(MediaAccessToken, client.app.state.media_sessions._token_hash(first_token))
        assert access is not None
        access.expires_at = utc_now_naive() - timedelta(seconds=1)
        session.commit()

    reopened = client.get(f"/api/v1/parse/jobs/{job_id}", headers=auth_headers)
    assert reopened.status_code == 200
    renewed = reopened.json()["job"]["result"]
    renewed_token = renewed["preview_url"].split("/media/", 1)[1].split("/", 1)[0]
    assert renewed_token != first_token
    assert renewed["media_expires_at"] == media_expires
    assert renewed["expires_at"] != first_expires
    renewed_expires = datetime.fromisoformat(renewed["expires_at"].replace("Z", "+00:00"))
    assert 890 <= (renewed_expires - datetime.now(UTC)).total_seconds() <= 910


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


def test_two_jobs_can_run_together_and_third_is_limited(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    service = ConcurrentParseService(client)
    client.app.state.parse_jobs.parse_service = service
    job_ids: list[str] = []
    try:
        for index in range(2):
            response = client.post(
                "/api/v1/parse",
                headers={**auth_headers, "Idempotency-Key": f"parse_concurrent_{index:02d}"},
                json={"text": f"https://example.com/video-{index}", "quality": "540p"},
            )
            assert response.status_code == 202
            job_ids.append(response.json()["job"]["job_id"])

        for job_id in job_ids:
            wait_for_status(client, job_id, auth_headers, {"processing"})

        limited = client.post(
            "/api/v1/parse",
            headers={**auth_headers, "Idempotency-Key": "parse_concurrent_03"},
            json={"text": "https://example.com/video-3", "quality": "540p"},
        )
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "PARSE_CONCURRENCY_LIMIT"
        assert service.max_active == 2
    finally:
        client.portal.call(service.release.set)

    for job_id in job_ids:
        wait_for_status(client, job_id, auth_headers, {"ready"})


def test_history_is_user_bound_does_not_issue_tokens_and_reopens_ready_result(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client.app.state.parse_jobs.parse_service = SuccessfulParseService(client)
    created = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "parse_history_test_01"},
        json={"text": "https://example.com/history", "quality": "720p"},
    )
    job_id = created.json()["job"]["job_id"]
    ready = wait_for_status(client, job_id, auth_headers, {"ready"})

    with client.app.state.database.session_factory() as session:
        token_count_before = len(list(session.scalars(select(MediaAccessToken))))
    history = client.get("/api/v1/parse/jobs?limit=10", headers=auth_headers)
    with client.app.state.database.session_factory() as session:
        token_count_after = len(list(session.scalars(select(MediaAccessToken))))

    assert history.status_code == 200
    item = history.json()["jobs"][0]
    assert item["job_id"] == job_id
    assert item["status"] == "ready"
    assert item["media_available"] is True
    assert item["summary"]["title"] == "持久任务"
    assert "result" not in item
    assert "preview_url" not in item
    assert token_count_after == token_count_before

    reopened = client.get(f"/api/v1/parse/jobs/{job_id}", headers=auth_headers)
    assert reopened.json()["job"]["result"]["download_url"].endswith("/download")
    assert reopened.json()["job"]["source_url"] == "https://example.com/history"
    assert ready["result"]["requested_quality"] == "720p"

    second_token = client.post("/api/v1/auth/wechat", json={"code": "history-other-user"}).json()[
        "token"
    ]
    other_history = client.get(
        "/api/v1/parse/jobs",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert other_history.json()["jobs"] == []


def test_history_marks_cleaned_media_expired_without_losing_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client.app.state.parse_jobs.parse_service = SuccessfulParseService(client)
    created = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "parse_history_expired_01"},
        json={"text": "https://example.com/expired-history", "quality": "original"},
    )
    job_id = created.json()["job"]["job_id"]
    ready = wait_for_status(client, job_id, auth_headers, {"ready"})
    session_id = ready["result"]["session_id"]
    with client.app.state.database.session_factory() as session:
        media = session.get(MediaSessionRecord, session_id)
        assert media is not None
        media.expires_at = utc_now_naive() - timedelta(seconds=1)
        session.commit()

    history = client.get("/api/v1/parse/jobs", headers=auth_headers).json()["jobs"]
    item = next(value for value in history if value["job_id"] == job_id)
    assert item["status"] == "expired"
    assert item["media_available"] is False
    assert item["summary"]["title"] == "持久任务"


def test_parse_requires_idempotency_key(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/parse",
        headers=auth_headers,
        json={"text": "https://example.com/video"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_INVALID"


def test_new_job_is_rejected_when_safe_disk_reserve_is_exhausted(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.parse_jobs.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=100, used=100, free=0),
    )
    response = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "parse_job_disk_full_01"},
        json={"text": "https://example.com/video", "quality": "540p"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_BUSY"


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
