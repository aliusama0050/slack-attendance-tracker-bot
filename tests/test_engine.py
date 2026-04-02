import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import process_attendance

KARACHI = ZoneInfo("Asia/Karachi")


def _make_event(text, user="U12345", ts=None):
    """Helper to create a mock Slack event dict."""
    if ts is None:
        ts = str(datetime.now(KARACHI).timestamp())
    return {"text": text, "user": user, "ts": ts}


def _make_mocks():
    resolver = MagicMock()
    resolver.resolve_user_id.return_value = "John Doe"
    resolver.resolve_jibble_name.return_value = "Abdul Haseeb"
    sheets = MagicMock()
    return resolver, sheets


class TestCheckin:
    @patch("engine.datetime")
    def test_new_checkin_creates_row(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 4, 2, 10, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = None

        process_attendance(
            _make_event("Check in 10:47 am"), resolver, sheets
        )

        sheets.append_row.assert_called_once_with(
            "John Doe", "2026-04-02", "10:47 am", "", ""
        )

    @patch("engine.datetime")
    def test_duplicate_checkin_ignored(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 4, 2, 10, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = {
            "row_number": 5,
            "name": "John Doe",
            "date": "2026-04-02",
            "checkin": "9:00 AM",
            "checkout": "",
            "duration": "",
        }

        process_attendance(
            _make_event("Check in 10:47 am"), resolver, sheets
        )

        sheets.append_row.assert_not_called()
        sheets.update_row.assert_not_called()


class TestCheckout:
    @patch("engine.datetime")
    def test_same_day_checkout_updates_row(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 4, 2, 23, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = {
            "row_number": 5,
            "name": "John Doe",
            "date": "2026-04-02",
            "checkin": "8:10 PM",
            "checkout": "",
            "duration": "",
        }

        process_attendance(
            _make_event("Checkout 11:00 PM"), resolver, sheets
        )

        sheets.update_row.assert_called_once_with(5, "11:00 PM", "2h 50m")

    @patch("engine.datetime")
    def test_overnight_checkout_finds_yesterday(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 4, 2, 2, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()

        # No row today, but row yesterday
        def find_row_side_effect(name, date):
            if date == "2026-04-01":
                return {
                    "row_number": 10,
                    "name": "John Doe",
                    "date": "2026-04-01",
                    "checkin": "10:00 PM",
                    "checkout": "",
                    "duration": "",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

        process_attendance(
            _make_event("Checkout 2:00 am"), resolver, sheets
        )

        sheets.update_row.assert_called_once_with(10, "2:00 am", "4h 0m")

    @patch("engine.datetime")
    def test_checkout_no_row_creates_na(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 4, 2, 17, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = None

        process_attendance(
            _make_event("Checkout 5:00 pm"), resolver, sheets
        )

        sheets.append_row.assert_called_once_with(
            "John Doe", "2026-04-02", "N/A", "5:00 pm", "N/A"
        )


class TestJibble:
    @patch("engine.get_event_time", return_value="10:00 AM")
    @patch("engine.datetime")
    def test_jibble_in_creates_row(self, mock_dt, mock_get_time):
        mock_dt.now.return_value = datetime(2026, 4, 2, 10, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = None

        event = _make_event("Haseeb jibbled in via Web (Chrome)")
        process_attendance(event, resolver, sheets)

        resolver.resolve_jibble_name.assert_called_once_with("Haseeb")
        sheets.append_row.assert_called_once_with(
            "Abdul Haseeb", "2026-04-02", "10:00 AM", "", ""
        )

    @patch("engine.get_event_time", return_value="6:00 PM")
    @patch("engine.datetime")
    def test_jibble_out_updates_row(self, mock_dt, mock_get_time):
        mock_dt.now.return_value = datetime(2026, 4, 2, 18, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = {
            "row_number": 7,
            "name": "Abdul Haseeb",
            "date": "2026-04-02",
            "checkin": "10:00 AM",
            "checkout": "",
            "duration": "",
        }

        event = _make_event("Haseeb jibbled out via Web (Chrome)")
        process_attendance(event, resolver, sheets)

        resolver.resolve_jibble_name.assert_called_once_with("Haseeb")
        sheets.update_row.assert_called_once_with(7, "6:00 PM", "8h 0m")


class TestSkip:
    def test_zapier_message_skipped(self):
        resolver, sheets = _make_mocks()
        process_attendance(
            _make_event("Good Afternoon Team! Sent by Zapier"), resolver, sheets
        )
        sheets.append_row.assert_not_called()
        sheets.update_row.assert_not_called()

    def test_random_message_skipped(self):
        resolver, sheets = _make_mocks()
        process_attendance(
            _make_event("test"), resolver, sheets
        )
        sheets.append_row.assert_not_called()
        sheets.update_row.assert_not_called()
