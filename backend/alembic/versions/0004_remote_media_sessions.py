"""Allow media sessions to stream a validated remote HTTPS source on demand."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_remote_media_sessions"
down_revision: str | None = "0003_parse_jobs_media_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("media_sessions") as batch:
        batch.alter_column("file_path", existing_type=sa.String(length=1024), nullable=True)
        batch.add_column(sa.Column("upstream_url", sa.String(length=4096), nullable=True))
        batch.add_column(sa.Column("required_headers_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("media_sessions") as batch:
        batch.drop_column("required_headers_json")
        batch.drop_column("upstream_url")
        batch.alter_column("file_path", existing_type=sa.String(length=1024), nullable=False)
