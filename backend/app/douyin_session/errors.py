from __future__ import annotations

from ..errors import AppError


def session_disabled() -> AppError:
    return AppError("DOUYIN_SESSION_DISABLED", "抖音专用会话功能未启用", status_code=503)


def session_config_invalid() -> AppError:
    return AppError("DOUYIN_SESSION_CONFIG_INVALID", "抖音专用会话配置无效或未完成", status_code=503)


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


def session_page_failed() -> AppError:
    return AppError(
        "DOUYIN_SESSION_PAGE_FAILED",
        "抖音作品页面加载异常，请稍后重试",
        status_code=502,
        retryable=True,
    )


def session_login_required() -> AppError:
    return AppError(
        "DOUYIN_SESSION_LOGIN_REQUIRED",
        "抖音专用会话未处于登录状态，请由运营者重新手动登录",
        status_code=503,
    )


def session_timeout() -> AppError:
    return AppError(
        "DOUYIN_SESSION_TIMEOUT",
        "抖音专用会话解析超时，请稍后重试",
        status_code=504,
        retryable=True,
    )


def login_incomplete() -> AppError:
    return AppError(
        "DOUYIN_SESSION_LOGIN_INCOMPLETE",
        "未检测到有效的抖音登录会话，请完成手动登录后再保存",
        status_code=400,
    )


def session_media_not_found() -> AppError:
    return AppError(
        "DOUYIN_SESSION_MEDIA_NOT_FOUND",
        "未在目标抖音作品的主播放器中找到可验证的视频媒体",
        status_code=502,
        retryable=True,
    )


def session_player_not_found() -> AppError:
    return AppError(
        "DOUYIN_SESSION_PLAYER_NOT_FOUND",
        "目标抖音作品未找到可用主播放器",
        status_code=502,
        retryable=True,
    )
