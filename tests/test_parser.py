import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from msg_parser import parse_message


class TestParseCheckin:
    def test_check_in_with_time(self):
        r = parse_message("Check in 10:47 am")
        assert r.action == "checkin"
        assert r.time_str == "10:47 am"
        assert r.is_jibble is False

    def test_checked_in_at_time(self):
        r = parse_message("checked in at 8:10pm")
        assert r.action == "checkin"
        assert r.time_str == "8:10pm"

    def test_check_in_with_colon(self):
        r = parse_message("Check in : 8:10 am")
        assert r.action == "checkin"
        assert r.time_str == "8:10 am"

    def test_check_in_no_time(self):
        r = parse_message("Check in")
        assert r.action == "checkin"
        assert r.time_str is None

    def test_checked_in_uppercase(self):
        r = parse_message("CHECKED IN 9:00 AM")
        assert r.action == "checkin"
        assert r.time_str == "9:00 AM"


class TestParseCheckout:
    def test_checkout_with_time(self):
        r = parse_message("Checkout 11:54 pm")
        assert r.action == "checkout"
        assert r.time_str == "11:54 pm"

    def test_check_out_colon_time(self):
        r = parse_message("check out: 12:00am")
        assert r.action == "checkout"
        assert r.time_str == "12:00am"

    def test_checkout_colon_space(self):
        r = parse_message("Checkout: 1:39 am")
        assert r.action == "checkout"
        assert r.time_str == "1:39 am"

    def test_checked_out_uppercase(self):
        r = parse_message("CHECKED OUT 5:30 PM")
        assert r.action == "checkout"
        assert r.time_str == "5:30 PM"


class TestParseJibble:
    def test_jibble_in(self):
        r = parse_message("Haseeb jibbled in via Web (Chrome)")
        assert r.action == "checkin"
        assert r.is_jibble is True
        assert r.jibble_first_name == "Haseeb"
        assert r.time_str is None

    def test_jibble_out(self):
        r = parse_message("Sara jibbled out via Web (Chrome)")
        assert r.action == "checkout"
        assert r.is_jibble is True
        assert r.jibble_first_name == "Sara"


class TestParseSkip:
    def test_zapier_message(self):
        r = parse_message("Good Afternoon Team! Sent by Zapier")
        assert r.action == "skip"

    def test_zapier_case_insensitive(self):
        r = parse_message("Reminder: daily standup SENT BY ZAPIER")
        assert r.action == "skip"

    def test_random_message(self):
        r = parse_message("test")
        assert r.action == "skip"

    def test_empty_message(self):
        r = parse_message("")
        assert r.action == "skip"

    def test_greeting(self):
        r = parse_message("Good morning everyone!")
        assert r.action == "skip"
