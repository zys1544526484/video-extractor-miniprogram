from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from ..errors import auth_required


def create_auth_token(user_id: int, secret: str, ttl_seconds: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "auth",
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_auth_token(token: str, secret: str) -> int:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError as error:
        raise auth_required("登录状态已失效") from error
    if payload.get("type") != "auth":
        raise auth_required("登录凭证类型无效")
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as error:
        raise auth_required("登录凭证无效") from error

