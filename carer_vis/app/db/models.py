# app/db/models.py
from __future__ import annotations
from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    BigInteger,
    Date,
    DateTime,
    Text,
    SmallInteger,
)

metadata = MetaData()

patients = Table(
    "patients",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("chat_id", BigInteger, nullable=False),
    Column("name", String(100), nullable=False),
)

pills_day = Table(
    "pills_day",
    metadata,
    Column("patient_id", String(40), primary_key=True),
    Column("date_kyiv", Date, primary_key=True),
    Column("dose", String(16), primary_key=True),  # 'morning' | 'evening'
    Column("label", String(120), nullable=False),
    Column("reminder_ts", DateTime, nullable=True),  # UTC naive
    Column("confirm_ts", DateTime, nullable=True),  # UTC naive
    Column("confirm_via", String(10), nullable=True),  # 'button' | 'text'
    Column("escalated_ts", DateTime, nullable=True),  # UTC naive
)

bp_readings = Table(
    "bp_readings",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("patient_id", String(40), nullable=False),
    Column("ts_utc", DateTime, nullable=False),
    Column("side", String(10), nullable=False),  # 'left' | 'right'
    Column("sys", SmallInteger, nullable=False),
    Column("dia", SmallInteger, nullable=False),
    Column("pulse", SmallInteger, nullable=False),
    Column("flags", String(40), nullable=True),  # may contain 'out_of_range'
    Column("escalated_ts", DateTime, nullable=True),
)

health_status = Table(
    "health_status",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("patient_id", String(40), nullable=False),
    Column("ts_utc", DateTime, nullable=False),
    Column("text", Text, nullable=False),
    Column("alert_match", String(200), nullable=True),
    Column("escalated_ts", DateTime, nullable=True),
)
