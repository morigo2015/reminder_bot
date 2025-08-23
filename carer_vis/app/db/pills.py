from __future__ import annotations
from typing import Optional, Tuple
from datetime import date
from app.db.pool import pool


async def upsert_reminder(patient_id: str, d: date, dose: str, label: str) -> None:
    sql = (
        "INSERT INTO pills_day (patient_id, date_kyiv, dose, label, reminder_ts) "
        "VALUES (%s, %s, %s, %s, UTC_TIMESTAMP()) "
        "ON DUPLICATE KEY UPDATE "
        "  reminder_ts = COALESCE(reminder_ts, VALUES(reminder_ts)), "
        "  label = VALUES(label)"
    )
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (patient_id, d, dose, label))


async def has_reminder_row(patient_id: str, d: date, dose: str) -> bool:
    sql = "SELECT reminder_ts IS NOT NULL FROM pills_day WHERE patient_id=%s AND date_kyiv=%s AND dose=%s"
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (patient_id, d, dose))
            row = await cur.fetchone()
            return bool(row and row[0])


async def set_confirm_if_empty(
    patient_id: str, d: date, dose: str, via: str
) -> Tuple[bool, Optional[str], bool]:
    """Return (changed, label, was_escalated)
    changed=True if confirm_ts was written now.
    """
    sql_get = "SELECT confirm_ts, escalated_ts, label FROM pills_day WHERE patient_id=%s AND date_kyiv=%s AND dose=%s"
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql_get, (patient_id, d, dose))
            row = await cur.fetchone()
            if not row:
                return False, None, False
            confirm_ts, escalated_ts, label = row
            if confirm_ts is None:
                sql_upd = (
                    "UPDATE pills_day SET confirm_ts=UTC_TIMESTAMP(), confirm_via=%s "
                    "WHERE patient_id=%s AND date_kyiv=%s AND dose=%s AND confirm_ts IS NULL"
                )
                await cur.execute(sql_upd, (via, patient_id, d, dose))
                changed = cur.rowcount > 0
                return changed, label, escalated_ts is not None


async def get_state(patient_id: str, d: date, dose: str):
    """
    Return (reminder_ts, confirm_ts) or None if row doesn't exist.
    Used by ticker to decide repeat eligibility (must still be unconfirmed,
    and enough time since initial reminder).
    """
    sql = "SELECT reminder_ts, confirm_ts FROM pills_day WHERE patient_id=%s AND date_kyiv=%s AND dose=%s"
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (patient_id, d, dose))
            return await cur.fetchone()


async def latest_unconfirmed(
    patient_id: str, today: date
) -> Optional[Tuple[date, str]]:
    """Find latest unconfirmed: prefer today, else previous day(s). Returns (date, dose)."""
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            # today first
            sql_today = (
                "SELECT date_kyiv, dose FROM pills_day "
                "WHERE patient_id=%s AND date_kyiv=%s AND reminder_ts IS NOT NULL AND confirm_ts IS NULL "
                "ORDER BY reminder_ts DESC LIMIT 1"
            )
            await cur.execute(sql_today, (patient_id, today))
            row = await cur.fetchone()
            if row:
                return row[0], row[1]
            # previous days
            sql_prev = (
                "SELECT date_kyiv, dose FROM pills_day "
                "WHERE patient_id=%s AND date_kyiv<%s AND reminder_ts IS NOT NULL AND confirm_ts IS NULL "
                "ORDER BY date_kyiv DESC, reminder_ts DESC LIMIT 1"
            )
            await cur.execute(sql_prev, (patient_id, today))
            row = await cur.fetchone()
            if row:
                return row[0], row[1]
            return None


async def overdue_candidates():
    sql = (
        "SELECT patient_id, date_kyiv, dose, TIMESTAMPDIFF(MINUTE, reminder_ts, UTC_TIMESTAMP()) AS age_min "
        "FROM pills_day WHERE reminder_ts IS NOT NULL AND confirm_ts IS NULL AND escalated_ts IS NULL"
    )
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql)
            return await cur.fetchall()


async def mark_escalated(patient_id: str, d: date, dose: str) -> bool:
    sql = (
        "UPDATE pills_day SET escalated_ts=UTC_TIMESTAMP() "
        "WHERE patient_id=%s AND date_kyiv=%s AND dose=%s AND escalated_ts IS NULL"
    )
    async with pool().acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (patient_id, d, dose))
            return cur.rowcount > 0
