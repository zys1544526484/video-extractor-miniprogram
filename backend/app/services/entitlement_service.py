from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ..database import Database
from ..errors import AppError
from ..models import AdUnlockEvent, RewardedAdAttempt, User


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def entitlement_payload(user: User, now: datetime | None = None) -> dict[str, object]:
    current = now or utc_now_naive()
    entitled = bool(user.unlock_until and user.unlock_until > current)
    return {
        "entitled": entitled,
        "unlock_until": iso_utc(user.unlock_until) if entitled else None,
        "server_time": iso_utc(current),
    }


def get_entitlement(database: Database, user_id: int) -> dict[str, object]:
    with database.session_factory() as session:
        user = session.get(User, user_id)
        if user is None:
            raise AppError("AUTH_REQUIRED", "用户不存在", status_code=401)
        return entitlement_payload(user)


def _attempt_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_rewarded_ad_attempt(
    database: Database,
    user_id: int,
    *,
    min_seconds: int,
    ttl_seconds: int,
) -> dict[str, object]:
    now = utc_now_naive()
    with database.session_factory() as session:
        user = session.get(User, user_id)
        if user is None:
            raise AppError("AUTH_REQUIRED", "用户不存在", status_code=401)
        if user.unlock_until and user.unlock_until > now:
            return {
                **entitlement_payload(user, now),
                "attempt_required": False,
                "attempt_token": None,
                "attempt_expires_at": None,
            }

        recent = session.scalar(
            select(func.count(RewardedAdAttempt.id)).where(
                RewardedAdAttempt.user_id == user_id,
                RewardedAdAttempt.created_at >= now - timedelta(minutes=10),
            )
        )
        if int(recent or 0) >= 5:
            raise AppError(
                "AD_ATTEMPT_RATE_LIMITED",
                "广告请求过于频繁，请稍后重试",
                status_code=429,
                retryable=True,
            )

        token = secrets.token_urlsafe(32)
        attempt = RewardedAdAttempt(
            user_id=user_id,
            token_hash=_attempt_hash(token),
            created_at=now,
            eligible_at=now + timedelta(seconds=min_seconds),
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        session.add(attempt)
        session.commit()
        return {
            **entitlement_payload(user, now),
            "attempt_required": True,
            "attempt_token": token,
            "attempt_expires_at": iso_utc(attempt.expires_at),
        }


def complete_rewarded_ad(
    database: Database,
    user_id: int,
    idempotency_key: str,
    attempt_token: str,
) -> dict[str, object]:
    now = utc_now_naive()
    with database.session_factory() as session:
        existing = session.scalar(
            select(AdUnlockEvent).where(AdUnlockEvent.idempotency_key == idempotency_key)
        )
        user = session.get(User, user_id)
        if user is None:
            raise AppError("AUTH_REQUIRED", "用户不存在", status_code=401)
        if existing is not None:
            if existing.user_id != user_id:
                raise AppError("AD_CONFIRM_INVALID", "广告确认凭证无效", status_code=403)
            return entitlement_payload(user, now)
        if user.unlock_until and user.unlock_until > now:
            return entitlement_payload(user, now)

        attempt = session.scalar(
            select(RewardedAdAttempt).where(
                RewardedAdAttempt.user_id == user_id,
                RewardedAdAttempt.token_hash == _attempt_hash(attempt_token),
            )
        )
        if attempt is None or attempt.consumed_at is not None or attempt.expires_at <= now:
            raise AppError("AD_CONFIRM_INVALID", "广告确认凭证无效或已过期", status_code=403)
        if attempt.eligible_at > now:
            raise AppError(
                "AD_CONFIRM_TOO_EARLY",
                "广告尚未达到奖励条件",
                status_code=409,
                retryable=True,
            )

        claimed = session.execute(
            update(RewardedAdAttempt)
            .where(
                RewardedAdAttempt.id == attempt.id,
                RewardedAdAttempt.consumed_at.is_(None),
                RewardedAdAttempt.expires_at > now,
            )
            .values(consumed_at=now)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            session.rollback()
            raise AppError("AD_CONFIRM_INVALID", "广告确认凭证无效或已使用", status_code=403)

        user.unlock_until = now + timedelta(hours=24)
        event = AdUnlockEvent(
            user_id=user_id,
            idempotency_key=idempotency_key,
            occurred_at=now,
            result="unlocked",
        )
        session.add(event)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            user = session.get(User, user_id)
        return entitlement_payload(user, now)
