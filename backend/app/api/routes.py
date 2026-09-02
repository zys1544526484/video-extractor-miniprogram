from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse, StreamingResponse

from ..errors import AppError, entitlement_required
from ..schemas import ParseRequest, WechatAuthRequest
from ..services.auth_service import create_session_token, exchange_wechat_code, get_or_create_user
from ..services.entitlement_service import complete_rewarded_ad, get_entitlement
from .dependencies import current_user_id

router = APIRouter(prefix="/api/v1")
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def ok(request: Request, **payload: Any) -> dict[str, Any]:
    return {"success": True, "request_id": request.state.request_id, **payload}


def safe_filename(platform: str, title: str) -> str:
    raw = f"{platform}_{title}".replace("\r", " ").replace("\n", " ")
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_.")
    digest = sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{(clean or 'video')[:72]}_{digest}.mp4"


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    return ok(request, status="ok", version=request.app.state.settings.version)


@router.post("/auth/wechat")
async def auth_wechat(body: WechatAuthRequest, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    openid = await exchange_wechat_code(body.code, settings)
    user = get_or_create_user(request.app.state.database, openid)
    token = create_session_token(user, settings)
    return ok(
        request,
        token=token,
        expires_in=settings.auth_token_ttl_seconds,
        user=get_entitlement(request.app.state.database, user.id),
    )


@router.get("/entitlement")
async def entitlement(request: Request, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    return ok(request, **get_entitlement(request.app.state.database, user_id))


@router.post("/entitlement/ad-complete")
async def ad_complete(
    request: Request,
    user_id: int = Depends(current_user_id),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if not idempotency_key or not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise AppError("URL_INVALID", "Idempotency-Key 格式无效")
    value = complete_rewarded_ad(request.app.state.database, user_id, idempotency_key)
    return ok(request, **value)


@router.post("/parse")
async def parse(
    body: ParseRequest,
    request: Request,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    result = await request.app.state.parse_service.parse(body.text, user_id)
    return ok(request, result=result.model_dump(mode="json"))


def local_file_response(file: Path, *, download: bool, filename: str, media_type: str) -> FileResponse:
    return FileResponse(
        file,
        media_type=media_type,
        filename=filename if download else None,
        content_disposition_type="attachment" if download else "inline",
    )


async def remote_stream_response(request: Request, media: Any, *, download: bool) -> StreamingResponse:
    range_header = request.headers.get("range")
    opened = await request.app.state.safe_http.open_stream(
        media.upstream_url,
        headers=media.required_headers,
        range_header=range_header,
    )
    response = opened.response
    declared_length = response.headers.get("content-length")
    if declared_length and declared_length.isdigit():
        if int(declared_length) > request.app.state.settings.max_video_bytes:
            await opened.close()
            raise AppError("MEDIA_TOO_LARGE", "视频超过 180MiB 限制")

    async def iterator():
        transferred = 0
        try:
            async for chunk in response.aiter_bytes():
                transferred += len(chunk)
                if transferred > request.app.state.settings.max_video_bytes:
                    raise AppError("MEDIA_TOO_LARGE", "视频超过 180MiB 限制")
                yield chunk
        finally:
            await opened.close()

    headers: dict[str, str] = {}
    for name in ("content-length", "content-range", "accept-ranges", "etag", "last-modified"):
        value = response.headers.get(name)
        if value:
            headers[name] = value
    if download:
        filename = safe_filename(media.platform, media.title)
        headers["content-disposition"] = f'attachment; filename="{filename}"'
    return StreamingResponse(
        iterator(),
        status_code=response.status_code,
        media_type=response.headers.get("content-type", media.mime_type).split(";", 1)[0],
        headers=headers,
    )


@router.get("/media/{token}/preview")
async def preview_media(token: str, request: Request):
    media = await request.app.state.media_sessions.get(token)
    if media.temporary_file:
        return local_file_response(
            media.temporary_file,
            download=False,
            filename=safe_filename(media.platform, media.title),
            media_type=media.mime_type,
        )
    return await remote_stream_response(request, media, download=False)


@router.get("/media/{token}/download")
async def download_media(token: str, request: Request, user_id: int = Depends(current_user_id)):
    media = await request.app.state.media_sessions.get(token)
    if media.user_id != user_id:
        raise AppError("AUTH_REQUIRED", "该下载链接不属于当前用户", status_code=403)
    current = get_entitlement(request.app.state.database, user_id)
    if not current["entitled"]:
        raise entitlement_required()
    if media.temporary_file:
        return local_file_response(
            media.temporary_file,
            download=True,
            filename=safe_filename(media.platform, media.title),
            media_type=media.mime_type,
        )
    return await remote_stream_response(request, media, download=True)
