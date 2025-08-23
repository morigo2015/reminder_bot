# app/db/pills.py
from __future__ import annotations
from typing import Optional, Tuple
from datetime import date
from sqlalchemy import select, update, func, text, and_, desc
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.db.session import engine
from app.db.models import pills_day


async def upsert_reminder(patient_id: str, d: date, dose: str, label: str) -> None:
    """
    INSERT ... ON DUPLICATE KEY UPDATE with COALESCE(reminder_ts, inserted.reminder_ts)
    to preserve the original reminder_ts if already set.
    """
    stmt = mysql_insert(pills_day).values(
        patient_id=patient_id,
        date_kyiv=d,
        dose=dose,
        label=label,
        reminder_ts=func.utc_timestamp(),
    )
    stmt = stmt.on_duplicate_key_update(
        reminder_ts=func.coalesce(pills_day.c.reminder_ts, stmt.inserted.reminder_ts),
        label=stmt.inserted.label,
    )
    async with engine().begin() as conn:
        await conn.execute(stmt)


async def has_reminder_row(patient_id: str, d: date, dose: str) -> bool:
    stmt = (
        select(pills_day.c.reminder_ts.is_not(None))
        .where(
            and_(
                pills_day.c.patient_id == patient_id,
                pills_day.c.date_kyiv == d,
                pills_day.c.dose == dose,
            )
        )
        .limit(1)
    )
    async with engine().begin() as conn:
        row = (await conn.execute(stmt)).first()
        return bool(row and row[0])


async def set_confirm_if_empty(
    patient_id: str, d: date, dose: str, via: str
) -> Tuple[bool, Optional[str], bool]:
    """
    Return (changed, label, was_escalated)
    changed=True if confirm_ts was written now.
    """
    sel = select(
        pills_day.c.confirm_ts, pills_day.c.escalated_ts, pills_day.c.label
    ).where(
        and_(
            pills_day.c.patient_id == patient_id,
            pills_day.c.date_kyiv == d,
            pills_day.c.dose == dose,
        )
    )
    async with engine().begin() as conn:
        row = (await conn.execute(sel)).first()
        if not row:
            return False, None, False
        confirm_ts, escalated_ts, label = row
        if confirm_ts is None:
            upd = (
                update(pills_day)
                .where(
                    and_(
                        pills_day.c.patient_id == patient_id,
                        pills_day.c.date_kyiv == d,
                        pills_day.c.dose == dose,
                        pills_day.c.confirm_ts.is_(None),
                    )
                )
                .values(confirm_ts=func.utc_timestamp(), confirm_via=via)
            )
            res = await conn.execute(upd)
            changed = res.rowcount > 0
            return changed, label, escalated_ts is not None
        return False, label, escalated_ts is not None


async def get_state(patient_id: str, d: date, dose: str):
    """
    Return (reminder_ts, confirm_ts) or None if row doesn't exist.
    Used by ticker to decide repeat eligibility.
    """
    stmt = (
        select(pills_day.c.reminder_ts, pills_day.c.confirm_ts)
        .where(
            and_(
                pills_day.c.patient_id == patient_id,
                pills_day.c.date_kyiv == d,
                pills_day.c.dose == dose,
            )
        )
        .limit(1)
    )
    async with engine().begin() as conn:
        row = (await conn.execute(stmt)).first()
        return tuple(row) if row else None


async def latest_unconfirmed(
    patient_id: str, today: date
) -> Optional[Tuple[date, str]]:
    """Find latest unconfirmed: prefer today, else previous day(s). Returns (date, dose)."""
    async with engine().begin() as conn:
        # 1) Today first (latest by reminder_ts)
        stmt_today = (
            select(pills_day.c.date_kyiv, pills_day.c.dose)
            .where(
                and_(
                    pills_day.c.patient_id == patient_id,
                    pills_day.c.date_kyiv == today,
                    pills_day.c.reminder_ts.is_not(None),
                    pills_day.c.confirm_ts.is_(None),
                )
            )
            .order_by(desc(pills_day.c.reminder_ts))
            .limit(1)
        )
        row = (await conn.execute(stmt_today)).first()
        if row:
            return row[0], row[1]
        # 2) Previous days (latest by date_kyiv, reminder_ts)
        stmt_prev = (
            select(pills_day.c.date_kyiv, pills_day.c.dose)
            .where(
                and_(
                    pills_day.c.patient_id == patient_id,
                    pills_day.c.date_kyiv < today,
                    pills_day.c.reminder_ts.is_not(None),
                    pills_day.c.confirm_ts.is_(None),
                )
            )
            .order_by(desc(pills_day.c.date_kyiv), desc(pills_day.c.reminder_ts))
            .limit(1)
        )
        row = (await conn.execute(stmt_prev)).first()
        if row:
            return row[0], row[1]
        return None


async def overdue_candidates():
    """
    Return rows of (patient_id, date_kyiv, dose, age_min) for all unconfirmed & not escalated reminders.
    """
    age_min = func.timestampdiff(
        text("MINUTE"), pills_day.c.reminder_ts, func.utc_timestamp()
    ).label("age_min")
    stmt = select(
        pills_day.c.patient_id, pills_day.c.date_kyiv, pills_day.c.dose, age_min
    ).where(
        and_(
            pills_day.c.reminder_ts.is_not(None),
            pills_day.c.confirm_ts.is_(None),
            pills_day.c.escalated_ts.is_(None),
        )
    )
    async with engine().begin() as conn:
        rows = (await conn.execute(stmt)).all()
        return [tuple(r) for r in rows]


async def mark_escalated(patient_id: str, d: date, dose: str) -> bool:
    stmt = (
        update(pills_day)
        .where(
            and_(
                pills_day.c.patient_id == patient_id,
                pills_day.c.date_kyiv == d,
                pills_day.c.dose == dose,
                pills_day.c.escalated_ts.is_(None),
            )
        )
        .values(escalated_ts=func.utc_timestamp())
    )
    async with engine().begin() as conn:
        res = await conn.execute(stmt)
        return res.rowcount > 0
