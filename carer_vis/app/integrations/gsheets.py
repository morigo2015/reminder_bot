# app/integrations/gsheets.py
from __future__ import annotations

import asyncio
import logging
from typing import List

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

from app import config
from app.util.retry import with_retry

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _creds() -> Credentials:
    """
    Build service-account credentials from a JSON file path.
    Single service account is used across all patient workbooks.
    """
    return Credentials.from_service_account_file(
        config.GSHEETS_CREDENTIALS_PATH, scopes=SCOPES
    )


def _fetch_values_blocking(spreadsheet_id: str, sheet_name: str) -> List[List[str]]:
    """
    Blocking: fetch A:B values from given sheet. Runs under asyncio.to_thread().
    """
    service = build("sheets", "v4", credentials=_creds(), cache_discovery=False)
    range_a1 = f"{sheet_name}!A1:B"
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_a1)
        .execute()
    )
    values = resp.get("values", []) or []
    return values


async def fetch_schedule_values(
    spreadsheet_id: str, sheet_name: str
) -> list[list[str]]:
    """
    Fetch schedule sheet values with retry + backoff, without blocking the event loop.
    """
    logger.debug(
        "gsheets: fetching values spreadsheet_id=%s sheet=%s",
        spreadsheet_id,
        sheet_name,
    )

    def _do():
        return _fetch_values_blocking(spreadsheet_id, sheet_name)

    # with_retry should handle backoff/retries; we run the blocking call in a thread
    values = await with_retry(asyncio.to_thread, _do)
    logger.debug("gsheets: fetched %d rows", len(values))
    return values
