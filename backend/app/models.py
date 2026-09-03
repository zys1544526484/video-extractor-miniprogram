from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    unlock_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    ad_events: Mapped[list[AdUnlockEvent]] = relationship(back_populates="user")


class AdUnlockEvent(Base):
    __tablename__ = "ad_unlock_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    result: Mapped[str] = mapped_column(String(32), default="unlocked")

    user: Mapped[User] = relationship(back_populates="ad_events")


Index("ix_ad_unlock_events_user_occurred", AdUnlockEvent.user_id, AdUnlockEvent.occurred_at)


class RewardedAdAttempt(Base):
    __tablename__ = "rewarded_ad_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    eligible_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index(
    "ix_rewarded_ad_attempts_user_created",
    RewardedAdAttempt.user_id,
    RewardedAdAttempt.created_at,
)
