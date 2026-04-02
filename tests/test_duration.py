import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from duration import calculate_duration, normalize_time


class TestNormalizeTime:
    def test_pm_no_space(self):
        assert normalize_time("8:10pm") == datetime.time(20, 10)

    def test_pm_with_space(self):
        assert normalize_time("8:10 PM") == datetime.time(20, 10)

    def test_am_with_leading_zero(self):
        assert normalize_time("08:10 AM") == datetime.time(8, 10)

    def test_24_hour(self):
        assert normalize_time("14:30") == datetime.time(14, 30)

    def test_midnight(self):
        assert normalize_time("12:00am") == datetime.time(0, 0)

    def test_noon(self):
        assert normalize_time("12:00pm") == datetime.time(12, 0)

    def test_invalid(self):
        assert normalize_time("garbage") is None

    def test_empty(self):
        assert normalize_time("") is None


class TestCalculateDuration:
    def test_same_day_duration(self):
        assert calculate_duration("9:00 AM", "5:00 PM") == "8h 0m"

    def test_evening_duration(self):
        assert calculate_duration("8:10 PM", "11:00 PM") == "2h 50m"

    def test_overnight_duration(self):
        assert calculate_duration("10:00 PM", "2:00 AM") == "4h 0m"

    def test_na_checkin(self):
        assert calculate_duration("N/A", "5:00 PM") == "N/A"

    def test_parse_error_checkin(self):
        assert calculate_duration("garbage", "5:00 PM") == "Parse Error"

    def test_parse_error_checkout(self):
        assert calculate_duration("9:00 AM", "garbage") == "Parse Error"

    def test_short_duration(self):
        assert calculate_duration("9:00 AM", "9:30 AM") == "0h 30m"

    def test_various_formats(self):
        # All these should produce the same result
        assert calculate_duration("8:10pm", "11:00pm") == "2h 50m"
        assert calculate_duration("8:10 PM", "11:00 PM") == "2h 50m"
        assert calculate_duration("20:10", "23:00") == "2h 50m"

    def test_zero_duration(self):
        assert calculate_duration("9:00 AM", "9:00 AM") == "0h 0m"
