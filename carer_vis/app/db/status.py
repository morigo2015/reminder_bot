# app/db/status.py
from __future__ import annotations
import logging
from sqlalchemy import insert, func
from app.db.session import engine
from app.db.models import health_status

logger = logging.getLogger(__name__)


async def insert_status(patient_id: str, text: str, alert_match: str | None) -> None:
    logger.debug(
        "DB: Health status inserted - patient=%s, text=%s, alert_match=%s",
        patient_id, text[:50] + "..." if len(text) > 50 else text, alert_match
    )
    stmt = insert(health_status).values(
        patient_id=patient_id,
        ts_utc=func.utc_timestamp(),
        text=text,
        alert_match=alert_match,
    )
    async with engine().begin() as conn:
        await conn.execute(stmt)
