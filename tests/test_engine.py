import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch LLM parser to always return None (use regex fallback) for all engine tests
import llm_parser
llm_parser._parser = None
_original_get = llm_parser.get_llm_parser
llm_parser.get_llm_parser = lambda: None

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

        # Only return a row for today (not for past dates)
        def find_row_side_effect(name, date):
            if date == "2026-04-02":
                return {
                    "row_number": 5,
                    "name": "John Doe",
                    "date": "2026-04-02",
                    "checkin": "9:00 AM",
                    "checkout": "",
                    "duration": "",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

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

        sheets.update_row.assert_called_once_with("John Doe", 5, "11:00 PM", "2h 50m")

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

        sheets.update_row.assert_called_once_with("John Doe", 10, "2:00 am", "4h 0m")

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
        sheets.update_row.assert_called_once_with("Abdul Haseeb", 7, "6:00 PM", "8h 0m")


class TestMissedCheckout:
    @patch("engine.datetime")
    def test_checkin_auto_closes_missed_checkout(self, mock_dt):
        """Check-in on day 2 should mark day 1's empty checkout as 'Missed'."""
        mock_dt.now.return_value = datetime(2026, 4, 2, 9, 30, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()

        def find_row_side_effect(name, date):
            if date == "2026-04-01":
                return {
                    "row_number": 5,
                    "date": "2026-04-01",
                    "checkin": "9:00 AM",
                    "checkout": "",
                    "duration": "",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

        process_attendance(
            _make_event("Check in 9:30 am"), resolver, sheets
        )

        # Should auto-close yesterday's row
        sheets.update_row.assert_called_once_with("John Doe", 5, "Missed", "Missed")
        # Should still create today's row
        sheets.append_row.assert_called_once_with(
            "John Doe", "2026-04-02", "9:30 am", "", ""
        )

    @patch("engine.datetime")
    def test_checkin_skips_already_closed_yesterday(self, mock_dt):
        """If yesterday's row has a checkout, don't mark it as missed."""
        mock_dt.now.return_value = datetime(2026, 4, 2, 9, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()

        def find_row_side_effect(name, date):
            if date == "2026-04-01":
                return {
                    "row_number": 5,
                    "date": "2026-04-01",
                    "checkin": "9:00 AM",
                    "checkout": "5:00 PM",
                    "duration": "8h 0m",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

        process_attendance(
            _make_event("Check in 9:00 am"), resolver, sheets
        )

        # Should NOT auto-close (yesterday already closed)
        sheets.update_row.assert_not_called()
        sheets.append_row.assert_called_once()

    @patch("engine.datetime")
    def test_checkout_finds_multi_day_old_row(self, mock_dt):
        """Checkout should find unclosed rows up to 7 days back (e.g. Friday→Monday)."""
        # It's Monday Apr 6, unclosed row from Friday Apr 3
        mock_dt.now.return_value = datetime(2026, 4, 6, 9, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()

        def find_row_side_effect(name, date):
            if date == "2026-04-03":
                return {
                    "row_number": 8,
                    "date": "2026-04-03",
                    "checkin": "10:00 PM",
                    "checkout": "",
                    "duration": "",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

        process_attendance(
            _make_event("Checkout 6:00 am"), resolver, sheets
        )

        sheets.update_row.assert_called_once_with(
            "John Doe", 8, "6:00 am", "8h 0m"
        )


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


class TestCheckoutGuard:
    @patch("engine.datetime")
    def test_duplicate_checkout_ignored(self, mock_dt):
        """Second checkout on same row should be ignored (not overwritten)."""
        mock_dt.now.return_value = datetime(2026, 4, 2, 23, 30, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = {
            "row_number": 5,
            "date": "2026-04-02",
            "checkin": "8:00 AM",
            "checkout": "11:00 PM",
            "duration": "15h 0m",
        }

        process_attendance(
            _make_event("Checkout 11:30 PM"), resolver, sheets
        )

        sheets.update_row.assert_not_called()

    @patch("engine.datetime")
    def test_edit_checkout_overwrites(self, mock_dt):
        """Checkout with is_edit=True should overwrite existing checkout."""
        mock_dt.now.return_value = datetime(2026, 4, 2, 23, 30, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = {
            "row_number": 5,
            "date": "2026-04-02",
            "checkin": "8:00 AM",
            "checkout": "11:00 PM",
            "duration": "15h 0m",
        }

        process_attendance(
            _make_event("Checkout 11:30 PM"), resolver, sheets, is_edit=True
        )

        sheets.update_row.assert_called_once_with("John Doe", 5, "11:30 PM", "15h 30m")


class TestEditCheckin:
    @patch("engine.datetime")
    def test_edit_checkin_updates_time(self, mock_dt):
        """Check-in edit should update existing check-in time."""
        mock_dt.now.return_value = datetime(2026, 4, 2, 10, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()

        def find_row_side_effect(name, date):
            if date == "2026-04-02":
                return {
                    "row_number": 5,
                    "date": "2026-04-02",
                    "checkin": "9:00 AM",
                    "checkout": "",
                    "duration": "",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

        process_attendance(
            _make_event("Check in 9:30 am"), resolver, sheets, is_edit=True
        )

        sheets.update_checkin.assert_called_once_with("John Doe", 5, "9:30 am")


class TestShiftMerge:
    @patch("engine.datetime")
    def test_different_shift_not_merged(self, mock_dt):
        """Checkout-only row at 12:19 AM + check-in at 8:35 AM → new row (different shifts)."""
        mock_dt.now.return_value = datetime(2026, 4, 2, 8, 35, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()

        def find_row_side_effect(name, date):
            if date == "2026-04-02":
                return {
                    "row_number": 5,
                    "date": "2026-04-02",
                    "checkin": "N/A",
                    "checkout": "12:19 AM",
                    "duration": "N/A",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

        process_attendance(
            _make_event("check in : 8:35 am"), resolver, sheets
        )

        # Should NOT merge — should create a new row
        sheets.update_checkin.assert_not_called()
        sheets.append_row.assert_called_once_with(
            "John Doe", "2026-04-02", "8:35 am", "", ""
        )

    @patch("engine.datetime")
    def test_same_shift_merged(self, mock_dt):
        """Checkout-only row at 11:00 PM + check-in at 7:00 PM → merge (same evening shift)."""
        mock_dt.now.return_value = datetime(2026, 4, 2, 19, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()

        def find_row_side_effect(name, date):
            if date == "2026-04-02":
                return {
                    "row_number": 5,
                    "date": "2026-04-02",
                    "checkin": "N/A",
                    "checkout": "11:00 PM",
                    "duration": "N/A",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

        process_attendance(
            _make_event("Check in: 7:00 pm"), resolver, sheets
        )

        # Should merge — fill in check-in and recalculate duration
        sheets.update_checkin.assert_called_once_with("John Doe", 5, "7:00 pm")
        sheets.update_row.assert_called_once_with("John Doe", 5, "11:00 PM", "4h 0m")


class TestAutoCloseMultiple:
    @patch("engine.datetime")
    def test_auto_close_multiple_unclosed_days(self, mock_dt):
        """Check-in should auto-close ALL unclosed rows, not just the first."""
        mock_dt.now.return_value = datetime(2026, 4, 4, 9, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()

        def find_row_side_effect(name, date):
            if date == "2026-04-03":
                return {
                    "row_number": 8,
                    "date": "2026-04-03",
                    "checkin": "9:00 AM",
                    "checkout": "",
                    "duration": "",
                }
            if date == "2026-04-02":
                return {
                    "row_number": 6,
                    "date": "2026-04-02",
                    "checkin": "10:00 AM",
                    "checkout": "",
                    "duration": "",
                }
            return None

        sheets.find_row.side_effect = find_row_side_effect

        process_attendance(
            _make_event("Check in 9:00 am"), resolver, sheets
        )

        # Both days should be auto-closed
        assert sheets.update_row.call_count == 2
        sheets.update_row.assert_any_call("John Doe", 8, "Missed", "Missed")
        sheets.update_row.assert_any_call("John Doe", 6, "Missed", "Missed")
        # And today's row created
        sheets.append_row.assert_called_once_with(
            "John Doe", "2026-04-04", "9:00 am", "", ""
        )


class TestLLMFallback:
    @patch("engine.llm_parse_message", return_value=None)
    @patch("engine.datetime")
    def test_falls_back_to_regex_when_llm_returns_none(self, mock_dt, mock_llm):
        """When LLM parser returns None, regex parser should handle the message."""
        mock_dt.now.return_value = datetime(2026, 4, 2, 10, 0, tzinfo=KARACHI)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resolver, sheets = _make_mocks()
        sheets.find_row.return_value = None

        process_attendance(
            _make_event("Check in 10:47 am"), resolver, sheets
        )

        mock_llm.assert_called_once()
        sheets.append_row.assert_called_once_with(
            "John Doe", "2026-04-02", "10:47 am", "", ""
        )
