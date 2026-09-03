"""Persist parse jobs and media capability tokens."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_parse_jobs_media_sessions"
down_revision: str | None = "0002_rewarded_ad_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parse_jobs",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_hash", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("requested_quality", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint("idempotency_hash"),
    )
    op.create_index("ix_parse_jobs_user_status", "parse_jobs", ["user_id", "status"])
    op.create_index(op.f("ix_parse_jobs_user_id"), "parse_jobs", ["user_id"])
    op.create_index(op.f("ix_parse_jobs_platform"), "parse_jobs", ["platform"])
    op.create_index(op.f("ix_parse_jobs_status"), "parse_jobs", ["status"])
    op.create_index(op.f("ix_parse_jobs_created_at"), "parse_jobs", ["created_at"])
    op.create_index(op.f("ix_parse_jobs_expires_at"), "parse_jobs", ["expires_at"])

    op.create_table(
        "media_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(op.f("ix_media_sessions_user_id"), "media_sessions", ["user_id"])
    op.create_index(op.f("ix_media_sessions_expires_at"), "media_sessions", ["expires_at"])

    op.create_table(
        "media_access_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["media_sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(op.f("ix_media_access_tokens_session_id"), "media_access_tokens", ["session_id"])
    op.create_index(op.f("ix_media_access_tokens_expires_at"), "media_access_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_media_access_tokens_expires_at"), table_name="media_access_tokens")
    op.drop_index(op.f("ix_media_access_tokens_session_id"), table_name="media_access_tokens")
    op.drop_table("media_access_tokens")
    op.drop_index(op.f("ix_media_sessions_expires_at"), table_name="media_sessions")
    op.drop_index(op.f("ix_media_sessions_user_id"), table_name="media_sessions")
    op.drop_table("media_sessions")
    op.drop_index(op.f("ix_parse_jobs_expires_at"), table_name="parse_jobs")
    op.drop_index(op.f("ix_parse_jobs_created_at"), table_name="parse_jobs")
    op.drop_index(op.f("ix_parse_jobs_status"), table_name="parse_jobs")
    op.drop_index(op.f("ix_parse_jobs_platform"), table_name="parse_jobs")
    op.drop_index(op.f("ix_parse_jobs_user_id"), table_name="parse_jobs")
    op.drop_index("ix_parse_jobs_user_status", table_name="parse_jobs")
    op.drop_table("parse_jobs")
