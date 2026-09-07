from __future__ import annotations

from ..errors import AppError


def session_disabled() -> AppError:
    return AppError("DOUYIN_SESSION_DISABLED", "抖音专用会话功能未启用", status_code=503)


def session_expired() -> AppError:
    return AppError("DOUYIN_SESSION_EXPIRED", "抖音专用会话已失效，请由运营者重新手动登录", status_code=503)


def risk_controlled() -> AppError:
    return AppError("DOUYIN_RISK_CONTROLLED", "抖音要求安全验证，已停止专用会话解析", status_code=503)


def session_bound_media() -> AppError:
    return AppError(
        "SESSION_BOUND_MEDIA",
        "该媒体只能依赖专用会话访问，当前不会传递会话凭据",
        status_code=502,
    )


def target_mismatch() -> AppError:
    return AppError("DOUYIN_SESSION_TARGET_MISMATCH", "专用会话未打开目标抖音作品", status_code=502)


def session_unavailable() -> AppError:
    return AppError("DOUYIN_SESSION_UNAVAILABLE", "抖音专用会话环境不可用", status_code=503)


def session_timeout() -> AppError:
    return AppError(
        "DOUYIN_SESSION_TIMEOUT",
        "抖音专用会话解析超时，请稍后重试",
        status_code=504,
        retryable=True,
    )
