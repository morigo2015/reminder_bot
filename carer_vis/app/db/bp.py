# app/db/bp.py
from __future__ import annotations
import logging
from sqlalchemy import insert, func
from app.db.session import engine
from app.db.models import bp_readings

logger = logging.getLogger(__name__)


async def insert_reading(
    patient_id: str, side: str, sys_v: int, dia_v: int, pulse_v: int, out_of_range: bool
) -> None:
    flags = "out_of_range" if out_of_range else None
    logger.debug(
        "DB: BP reading inserted - patient=%s, side=%s, bp=%s/%s, pulse=%s, out_of_range=%s",
        patient_id, side, sys_v, dia_v, pulse_v, out_of_range
    )
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
