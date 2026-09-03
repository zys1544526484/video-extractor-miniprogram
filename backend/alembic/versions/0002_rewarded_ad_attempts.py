"""Add server-issued rewarded-ad attempt tickets."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_rewarded_ad_attempts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rewarded_ad_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("eligible_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_rewarded_ad_attempts_user_created",
        "rewarded_ad_attempts",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rewarded_ad_attempts_created_at"),
        "rewarded_ad_attempts",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rewarded_ad_attempts_expires_at"),
        "rewarded_ad_attempts",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rewarded_ad_attempts_user_id"),
        "rewarded_ad_attempts",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rewarded_ad_attempts_user_id"), table_name="rewarded_ad_attempts")
    op.drop_index(op.f("ix_rewarded_ad_attempts_expires_at"), table_name="rewarded_ad_attempts")
    op.drop_index(op.f("ix_rewarded_ad_attempts_created_at"), table_name="rewarded_ad_attempts")
    op.drop_index("ix_rewarded_ad_attempts_user_created", table_name="rewarded_ad_attempts")
    op.drop_table("rewarded_ad_attempts")
