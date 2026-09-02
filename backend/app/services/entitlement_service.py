from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..database import Database
from ..errors import AppError
from ..models import AdUnlockEvent, User


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


def complete_rewarded_ad(database: Database, user_id: int, idempotency_key: str) -> dict[str, object]:
    now = utc_now_naive()
    with database.session_factory() as session:
        existing = session.scalar(
            select(AdUnlockEvent).where(AdUnlockEvent.idempotency_key == idempotency_key)
        )
        user = session.get(User, user_id)
        if user is None:
            raise AppError("AUTH_REQUIRED", "用户不存在", status_code=401)
        if existing is not None or (user.unlock_until and user.unlock_until > now):
            return entitlement_payload(user, now)

        recent = session.scalar(
            select(func.count(AdUnlockEvent.id)).where(
                AdUnlockEvent.user_id == user_id,
                AdUnlockEvent.occurred_at >= now - timedelta(minutes=10),
            )
        )
        if int(recent or 0) >= 5:
            raise AppError(
                "AD_CONFIRM_RATE_LIMITED",
                "广告确认过于频繁，请稍后重试",
                status_code=429,
                retryable=True,
            )

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

