"""SQLAlchemy engine and health-check helpers."""

from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url

from eea_backend.settings import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Create an engine suitable for the configured database backend."""

    is_sqlite = settings.database_url.startswith("sqlite")
    if is_sqlite:
        database = make_url(settings.database_url).database
        if database and database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            if isinstance(dbapi_connection, SQLiteConnection):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return engine


def check_database(engine: Engine) -> None:
    """Raise when the configured database cannot execute a trivial query."""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
