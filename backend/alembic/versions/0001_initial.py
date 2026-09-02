"""Create users and rewarded-ad audit tables."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("openid", sa.String(length=128), nullable=False),
        sa.Column("unlock_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_openid"), "users", ["openid"], unique=True)
    op.create_table(
        "ad_unlock_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_ad_unlock_events_user_occurred",
        "ad_unlock_events",
        ["user_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ad_unlock_events_occurred_at"),
        "ad_unlock_events",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ad_unlock_events_user_id"),
        "ad_unlock_events",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ad_unlock_events_user_id"), table_name="ad_unlock_events")
    op.drop_index(op.f("ix_ad_unlock_events_occurred_at"), table_name="ad_unlock_events")
    op.drop_index("ix_ad_unlock_events_user_occurred", table_name="ad_unlock_events")
    op.drop_table("ad_unlock_events")
    op.drop_index(op.f("ix_users_openid"), table_name="users")
    op.drop_table("users")
