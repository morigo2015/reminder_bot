# app/db/status.py
from __future__ import annotations
from sqlalchemy import insert, func
from app.db.session import engine
from app.db.models import health_status


async def insert_status(patient_id: str, text: str, alert_match: str | None) -> None:
    stmt = insert(health_status).values(
        patient_id=patient_id,
        ts_utc=func.utc_timestamp(),
        text=text,
        alert_match=alert_match,
    )
    async with engine().begin() as conn:
        await conn.execute(stmt)
