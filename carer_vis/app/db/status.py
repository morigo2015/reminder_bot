from __future__ import annotations
from typing import Optional
from app.db.pool import pool

async def insert_status(patient_id: str, text: str, alert_match: str | None) -> None:
    sql = (
        "INSERT INTO health_status (patient_id, ts_utc, text, alert_match) "
        "VALUES (%s, UTC_TIMESTAMP(), %s, %s)"
    )
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (patient_id, text, alert_match))
