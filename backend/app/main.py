from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import Settings, load_settings
from .database import Database
from .errors import AppError
from .parsers.registry import ParserRegistry
from .services.media_sessions import MediaSessionStore
from .services.parse_service import ParseService
from .services.safe_http import SafeHttpClient

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
logger = logging.getLogger("video_extractor")


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    # HTTPX logs the complete request URL at INFO. WeChat code2Session carries
    # AppSecret and the one-time login code in its query string, so those
    # libraries must never inherit the application INFO level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def error_payload(request: Request, error: AppError) -> dict[str, object]:
    return {
        "success": False,
        "request_id": getattr(request.state, "request_id", f"req_{uuid.uuid4().hex}"),
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or load_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(app_settings.database_url)
        database.create_schema()
        app_settings.temp_dir.mkdir(parents=True, exist_ok=True)
        safe_http = SafeHttpClient(
            timeout_seconds=app_settings.http_timeout_seconds,
            max_redirects=app_settings.max_redirects,
            max_video_bytes=app_settings.max_video_bytes,
        )
        media_sessions = MediaSessionStore(
            app_settings.media_session_ttl_seconds,
            app_settings.temp_dir,
            app_settings.temp_file_ttl_seconds,
        )
        registry = ParserRegistry(app_settings)
        app.state.settings = app_settings
        app.state.database = database
        app.state.safe_http = safe_http
        app.state.media_sessions = media_sessions
        app.state.parse_service = ParseService(app_settings, safe_http, registry, media_sessions)

        async def janitor() -> None:
            while True:
                await asyncio.sleep(60)
                await media_sessions.cleanup()

        task = asyncio.create_task(janitor())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await media_sessions.cleanup()
            database.close()

    app = FastAPI(title="视频提取 API", version=app_settings.version, lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        started = asyncio.get_running_loop().time()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        latency_ms = round((asyncio.get_running_loop().time() - started) * 1000, 1)
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                },
                ensure_ascii=False,
            )
        )
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        return JSONResponse(error_payload(request, error), status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        app_error = AppError("URL_INVALID", "请求参数无效", status_code=422)
        return JSONResponse(error_payload(request, app_error), status_code=422)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.exception("unhandled_error request_id=%s", getattr(request.state, "request_id", "unknown"))
        app_error = AppError("INTERNAL_ERROR", "服务暂时不可用", status_code=500, retryable=True)
        return JSONResponse(error_payload(request, app_error), status_code=500)

    app.include_router(router)
    return app


app = create_app()
