from __future__ import annotations

import hashlib

import httpx
from sqlalchemy import select

from ..config import Settings
from ..database import Database
from ..errors import AppError
from ..models import User
from ..security.tokens import create_auth_token


async def exchange_wechat_code(code: str, settings: Settings) -> str:
    if settings.mock_wechat_auth:
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:24]
        return f"mock_{digest}"
    params = {
        "appid": settings.wechat_app_id,
        "secret": settings.wechat_app_secret.get_secret_value(),
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get("https://api.weixin.qq.com/sns/jscode2session", params=params)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise AppError("AUTH_FAILED", "微信登录服务暂时不可用", status_code=502, retryable=True) from error
    openid = payload.get("openid")
    if not openid:
        raise AppError("AUTH_FAILED", "微信登录失败，请重试", status_code=401, retryable=True)
    return str(openid)


def get_or_create_user(database: Database, openid: str) -> User:
    with database.session_factory() as session:
        user = session.scalar(select(User).where(User.openid == openid))
        if user is None:
            user = User(openid=openid)
            session.add(user)
            session.commit()
            session.refresh(user)
        return user


def create_session_token(user: User, settings: Settings) -> str:
    return create_auth_token(
        user.id,
        settings.app_token_secret.get_secret_value(),
        settings.auth_token_ttl_seconds,
    )

