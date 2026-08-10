"""SQLAlchemy engine and health-check helpers."""

from sqlalchemy import Engine, create_engine, text

from eea_backend.settings import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Create an engine suitable for the configured database backend."""

    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    return create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)


def check_database(engine: Engine) -> None:
    """Raise when the configured database cannot execute a trivial query."""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
