import json
import logging
import os
import time

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_RETRIES = 3

HEADER_ROW = ["Date", "Check-In", "Check-Out", "Duration"]


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

    Each person gets their own worksheet tab named after them.
    Columns: A=Date, B=Check-In, C=Check-Out, D=Duration
    """

    def __init__(self, service_account_json: str, sheet_id: str):
        creds = _load_credentials(service_account_json)
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self.gc.open_by_key(sheet_id)

    def _get_or_create_worksheet(self, name: str) -> gspread.Worksheet:
        """Get the worksheet for a person, creating it if it doesn't exist."""
        try:
            return self.spreadsheet.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            logger.info("Creating new worksheet for '%s'", name)
            ws = self.spreadsheet.add_worksheet(title=name, rows=100, cols=4)
            ws.append_row(HEADER_ROW, value_input_option="USER_ENTERED")
            return ws

    @_retry_on_rate_limit
    def find_row(self, name: str, date: str) -> dict | None:
        """Search for a row matching date in the person's worksheet.

        Returns dict with row_number, date, checkin, checkout, duration
        or None if not found.
        """
        ws = self._get_or_create_worksheet(name)
        try:
            cells = ws.findall(date, in_column=1)
        except gspread.exceptions.APIError:
            logger.exception("Error searching for date=%s in sheet '%s'", date, name)
            return None

        for cell in cells:
            # Skip header row
            if cell.row == 1:
                continue
            row_values = ws.row_values(cell.row)
            if len(row_values) >= 1 and row_values[0] == date:
                return {
                    "row_number": cell.row,
                    "date": row_values[0] if len(row_values) > 0 else "",
                    "checkin": row_values[1] if len(row_values) > 1 else "",
                    "checkout": row_values[2] if len(row_values) > 2 else "",
                    "duration": row_values[3] if len(row_values) > 3 else "",
                }
        return None

    @_retry_on_rate_limit
    def append_row(
        self, name: str, date: str, checkin: str, checkout: str, duration: str
    ) -> None:
        """Append a new attendance row to the person's worksheet."""
        ws = self._get_or_create_worksheet(name)
        ws.append_row(
            [date, checkin, checkout, duration],
            value_input_option="USER_ENTERED",
        )
        logger.info("Appended row to '%s': %s | %s | %s | %s",
                     name, date, checkin, checkout, duration)

    @_retry_on_rate_limit
    def update_row(self, name: str, row_number: int, checkout: str, duration: str) -> None:
        """Update Check-Out (col C) and Duration (col D) in the person's worksheet."""
        ws = self._get_or_create_worksheet(name)
        ws.update_cell(row_number, 3, checkout)
        ws.update_cell(row_number, 4, duration)
        logger.info("Updated row %d in '%s': checkout=%s, duration=%s",
                     row_number, name, checkout, duration)

    @_retry_on_rate_limit
    def update_checkin(self, name: str, row_number: int, checkin: str) -> None:
        """Update Check-In (col B) in the person's worksheet."""
        ws = self._get_or_create_worksheet(name)
        ws.update_cell(row_number, 2, checkin)
        logger.info("Updated row %d in '%s': checkin=%s",
                     row_number, name, checkin)
