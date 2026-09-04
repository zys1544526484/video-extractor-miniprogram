from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


class Database:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite:///"):
            file_name = database_url.removeprefix("sqlite:///")
            if file_name != ":memory:":
                Path(file_name).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args, future=True)
        if database_url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, _record) -> None:
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                if database_url != "sqlite:///:memory:":
                    cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def verify_alembic_head(self) -> None:
        """Fail closed when a production database is not at the migration head."""
        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        config = Config(str(config_path))
        config.set_main_option("script_location", str(config_path.parent / "alembic"))
        expected_heads = set(ScriptDirectory.from_config(config).get_heads())
        with self.engine.connect() as connection:
            if not inspect(connection).has_table("alembic_version"):
                raise RuntimeError("生产数据库未完成 Alembic 迁移：缺少 alembic_version")
            applied = {
                row[0]
                for row in connection.execute(text("SELECT version_num FROM alembic_version"))
            }
        if applied != expected_heads:
            raise RuntimeError(
                f"生产数据库未到 Alembic head：expected={sorted(expected_heads)}, applied={sorted(applied)}"
            )

    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    def close(self) -> None:
        self.engine.dispose()
