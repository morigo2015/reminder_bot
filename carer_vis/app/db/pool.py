from __future__ import annotations
import aiomysql
from typing import Optional
from app import config

_pool: Optional[aiomysql.Pool] = None


async def init_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=config.DB["host"],
            port=config.DB["port"],
            user=config.DB["user"],
            password=config.DB["password"],
            db=config.DB["db"],
            autocommit=True,
            minsize=1,
            maxsize=5,
        )
    return _pool


def pool() -> aiomysql.Pool:
    assert _pool is not None, "DB pool is not initialized"
    return _pool
