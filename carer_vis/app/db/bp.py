from __future__ import annotations
from typing import Optional
from app.db.pool import pool

async def insert_reading(patient_id: str, side: str, sys_v: int, dia_v: int, pulse_v: int, out_of_range: bool) -> None:
    sql = (
        "INSERT INTO bp_readings (patient_id, ts_utc, side, sys, dia, pulse, flags) "
        "VALUES (%s, UTC_TIMESTAMP(), %s, %s, %s, %s, IF(%s, 'out_of_range', NULL))"
    )
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (patient_id, side, sys_v, dia_v, pulse_v, out_of_range))
