# app/db/bp.py
from __future__ import annotations
from sqlalchemy import insert, func
from app.db.session import engine
from app.db.models import bp_readings


async def insert_reading(
    patient_id: str, side: str, sys_v: int, dia_v: int, pulse_v: int, out_of_range: bool
) -> None:
    flags = "out_of_range" if out_of_range else None
    stmt = insert(bp_readings).values(
        patient_id=patient_id,
        ts_utc=func.utc_timestamp(),
        side=side,
        sys=sys_v,
        dia=dia_v,
        pulse=pulse_v,
        flags=flags,
    )
    async with engine().begin() as conn:
        await conn.execute(stmt)
