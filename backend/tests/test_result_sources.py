from __future__ import annotations

import json
import time
from datetime import timedelta

from app.models import MediaSessionRecord, ParseJob, utc_now_naive
from app.schemas import ParsePublicResult


class MultiSourceParseService:
    def __init__(self, client) -> None:
        self.client = client

    async def parse(self, text, user_id, quality, progress=None) -> ParsePublicResult:
        root = self.client.app.state.settings.temp_dir / f"multi-{user_id}"
        root.mkdir(parents=True, exist_ok=True)
        first = root / "first.mp4"
        second = root / "second.mp4"
        image = root / "cover.jpg"
        first.write_bytes(b"first-source")
        second.write_bytes(b"second-source")
        image.write_bytes(b"image-bytes")
        sessions = []
        for name, file, label in (
            ("source-1", first, "1080P H.264"),
            ("source-2", second, "720P H.264"),
        ):
            media = await self.client.app.state.media_sessions.create(
                user_id=user_id,
                platform="测试平台",
                title="多源视频",
                upstream_url=None,
                temporary_file=str(file),
                required_headers={},
                mime_type="video/mp4",
                size_bytes=file.stat().st_size,
            )
            sessions.append({
                "source_id": name,
                "session_id": media.session_id,
                "quality_label": label,
                "size_bytes": file.stat().st_size,
                "mime_type": "video/mp4",
            })
        image_media = await self.client.app.state.media_sessions.create(
            user_id=user_id,
            platform="测试平台",
            title="多源视频封面",
            upstream_url=None,
            temporary_file=str(image),
            required_headers={},
            mime_type="image/jpeg",
            size_bytes=image.stat().st_size,
        )
        return ParsePublicResult(
            session_id=sessions[0]["session_id"],
            platform="测试平台",
            title="多源视频",
            cover_url="",
            duration_seconds=12,
            size_bytes=first.stat().st_size,
            quality_label="1080P H.264",
            requested_quality=quality,
            preview_url="unused",
            download_url="unused",
            expires_at=sessions[0].get("expires_at") or image_media.expires_at,
            media_expires_at=image_media.expires_at,
            watermark_status="unknown",
            notice="",
            sources=sessions,
            images=[{
                "image_id": "cover",
                "session_id": image_media.session_id,
                "mime_type": "image/jpeg",
                "size_bytes": image.stat().st_size,
                "alt": "封面",
            }],
            share_text="多源视频\nhttps://example.com/video",
            selected_source_id="source-1",
        )


def wait_ready(client, job_id: str, headers: dict[str, str]) -> dict:
    deadline = time.time() + 3
    while time.time() < deadline:
        job = client.get(f"/api/v1/parse/jobs/{job_id}", headers=headers).json()["job"]
        if job["status"] == "ready":
            return job
        if job["status"] in {"failed", "cancelled", "expired"}:
            raise AssertionError(job)
        time.sleep(0.02)
    raise AssertionError("job did not become ready")


def test_ready_result_exposes_safe_multi_sources_and_images(client, auth_headers) -> None:
    client.app.state.parse_jobs.parse_service = MultiSourceParseService(client)
    response = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "multi_source_contract_01"},
        json={"text": "https://example.com/video", "quality": "original"},
    )
    assert response.status_code == 202
    job = wait_ready(client, response.json()["job"]["job_id"], auth_headers)
    result = job["result"]
    assert [item["source_id"] for item in result["sources"]] == ["source-1", "source-2"]
    assert result["sources"][0]["quality_label"] == "1080P H.264"
    assert result["sources"][1]["quality_label"] == "720P H.264"
    assert all("session_id" not in item for item in result["sources"])
    assert all("upstream_media_url" not in item for item in result["sources"])
    assert result["sources"][0]["download_url"].endswith("/download")
    assert result["sources"][0]["download_url"] != result["sources"][1]["download_url"]
    assert result["images"][0]["preview_url"].endswith("/preview")
    assert "session_id" not in result["images"][0]
    assert result["share_text"].startswith("多源视频")


def test_server_renews_selected_source_when_other_source_expires(client, auth_headers) -> None:
    client.app.state.parse_jobs.parse_service = MultiSourceParseService(client)
    response = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "multi_source_renew_01"},
        json={"text": "https://example.com/video", "quality": "original"},
    )
    job_id = response.json()["job"]["job_id"]
    wait_ready(client, job_id, auth_headers)

    # Simulate a client that selected source 2 and a later cleanup that expired
    # source 1.  The server must still issue source 2 and report it as selected.
    with client.app.state.database.session_factory() as session:
        job = session.get(ParseJob, job_id)
        stored = json.loads(job.result_json)
        stored["selected_source_id"] = "source-2"
        job.result_json = json.dumps(stored, ensure_ascii=False)
        source_one = session.get(MediaSessionRecord, stored["sources"][0]["session_id"])
        source_one.expires_at = utc_now_naive() - timedelta(seconds=1)
        session.commit()

    renewed = client.get(f"/api/v1/parse/jobs/{job_id}", headers=auth_headers)
    assert renewed.status_code == 200
    result = renewed.json()["job"]["result"]
    assert result["selected_source_id"] == "source-2"
    assert [item["source_id"] for item in result["sources"]] == ["source-2"]
    assert result["download_url"] == result["sources"][0]["download_url"]


def test_selected_source_is_persisted_on_job_and_returned_after_reopen(client, auth_headers) -> None:
    client.app.state.parse_jobs.parse_service = MultiSourceParseService(client)
    response = client.post(
        "/api/v1/parse",
        headers={**auth_headers, "Idempotency-Key": "multi_source_selection_01"},
        json={"text": "https://example.com/video", "quality": "original"},
    )
    job_id = response.json()["job"]["job_id"]
    wait_ready(client, job_id, auth_headers)

    selected = client.patch(
        f"/api/v1/parse/jobs/{job_id}/source",
        headers=auth_headers,
        json={"selected_source_id": "source-2"},
    )
    assert selected.status_code == 200
    assert selected.json()["job"]["result"]["selected_source_id"] == "source-2"

    reopened = client.get(f"/api/v1/parse/jobs/{job_id}", headers=auth_headers)
    reopened_result = reopened.json()["job"]["result"]
    assert reopened_result["selected_source_id"] == "source-2"
    assert reopened_result["download_url"].endswith("/download")
