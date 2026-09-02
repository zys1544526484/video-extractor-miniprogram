from __future__ import annotations


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


def auth_required(message: str = "请重新登录") -> AppError:
    return AppError("AUTH_REQUIRED", message, status_code=401)


def entitlement_required() -> AppError:
    return AppError("ENTITLEMENT_REQUIRED", "请先观看广告解锁下载", status_code=403)

