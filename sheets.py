import json
import logging
import os
import time

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_RETRIES = 3


def _retry_on_rate_limit(func):
    """Decorator that retries gspread calls on 429 rate limit errors."""
    def wrapper(*args, **kwargs):
        for attempt in range(MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except gspread.exceptions.APIError as e:
                if e.response.status_code == 429 and attempt < MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning("Google Sheets rate limit hit, retrying in %ds", wait)
                    time.sleep(wait)
                else:
                    raise
    return wrapper


def _load_credentials(service_account_json: str) -> Credentials:
    """Load Google credentials from a file path or raw JSON string."""
    if os.path.isfile(service_account_json):
        return Credentials.from_service_account_file(
            service_account_json, scopes=SCOPES
        )
    # Treat as raw JSON string (for Vercel / serverless)
    info = json.loads(service_account_json)
    return Credentials.from_service_account_info(info, scopes=SCOPES)


class GoogleSheetsClient:
    """Client for reading/writing attendance data to Google Sheets.

    Expected columns: A=Name, B=Date, C=Check-In, D=Check-Out, E=Duration
    """

    def __init__(self, service_account_json: str, sheet_id: str):
        creds = _load_credentials(service_account_json)
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(sheet_id).sheet1

    @_retry_on_rate_limit
    def find_row(self, name: str, date: str) -> dict | None:
        """Search for a row matching (name, date).

        Returns dict with row_number, name, date, checkin, checkout, duration
        or None if not found.
        """
        try:
            cells = self.sheet.findall(name, in_column=1)
        except gspread.exceptions.APIError:
            logger.exception("Error searching for name=%s", name)
            return None

        for cell in cells:
            row_values = self.sheet.row_values(cell.row)
            # Ensure row has at least 2 columns (Name, Date)
            if len(row_values) >= 2 and row_values[1] == date:
                return {
                    "row_number": cell.row,
                    "name": row_values[0] if len(row_values) > 0 else "",
                    "date": row_values[1] if len(row_values) > 1 else "",
                    "checkin": row_values[2] if len(row_values) > 2 else "",
                    "checkout": row_values[3] if len(row_values) > 3 else "",
                    "duration": row_values[4] if len(row_values) > 4 else "",
                }
        return None

    @_retry_on_rate_limit
    def append_row(
        self, name: str, date: str, checkin: str, checkout: str, duration: str
    ) -> None:
        """Append a new attendance row at the bottom of the sheet."""
        self.sheet.append_row(
            [name, date, checkin, checkout, duration],
            value_input_option="USER_ENTERED",
        )
        logger.info("Appended row: %s | %s | %s | %s | %s",
                     name, date, checkin, checkout, duration)

    @_retry_on_rate_limit
    def update_row(self, row_number: int, checkout: str, duration: str) -> None:
        """Update Check-Out (col D) and Duration (col E) for an existing row."""
        self.sheet.update_cell(row_number, 4, checkout)
        self.sheet.update_cell(row_number, 5, duration)
        logger.info("Updated row %d: checkout=%s, duration=%s",
                     row_number, checkout, duration)
