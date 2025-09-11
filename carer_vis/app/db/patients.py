# app/db/patients.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.db.session import engine
from app.db.models import patients


async def upsert_patient(pid: str, chat_id: int, name: str) -> None:
    """
    Create or update a patient row by id.
    """
    stmt = mysql_insert(patients).values(id=pid, chat_id=chat_id, name=name)
    stmt = stmt.on_duplicate_key_update(
        chat_id=stmt.inserted.chat_id,
        name=stmt.inserted.name,
    )
    async with engine().begin() as conn:
        await conn.execute(stmt)


async def exists_patient(pid: str) -> bool:
    """
    Return True if a patient with the given id exists.
    """
    stmt = select(patients.c.id).where(patients.c.id == pid).limit(1)
    async with engine().begin() as conn:
        row = (await conn.execute(stmt)).first()
        return row is not None
