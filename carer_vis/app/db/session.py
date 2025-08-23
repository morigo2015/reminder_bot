# app/db/session.py
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from app import config

_engine: AsyncEngine | None = None


def engine() -> AsyncEngine:
    """
    Lazily create a singleton AsyncEngine.
    Uses the already-installed aiomysql driver via SQLAlchemy's 'mysql+aiomysql'.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            f"mysql+aiomysql://{config.DB['user']}:{config.DB['password']}"
            f"@{config.DB['host']}:{config.DB['port']}/{config.DB['db']}",
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=0,
            echo=False,
        )
    return _engine
