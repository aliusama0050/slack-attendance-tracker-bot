import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from msg_parser import ParseResult
from llm_parser import LLMParser


def _make_mock_response(content: str):
    """Create a mock Groq API response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


class TestLLMParserCheckin:
    def test_checkin_with_time(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.return_value = _make_mock_response(
            '{"action": "checkin", "time": "10:47 am", "is_jibble": false, "jibble_first_name": null}'
        )

        result = parser.parse("Check in 10:47 am")

        assert result == ParseResult("checkin", "10:47 am", False, None)

    def test_checkin_no_time(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.return_value = _make_mock_response(
            '{"action": "checkin", "time": null, "is_jibble": false, "jibble_first_name": null}'
        )

        result = parser.parse("I'm starting work")

        assert result.action == "checkin"
        assert result.time_str is None


class TestLLMParserCheckout:
    def test_checkout_with_time(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.return_value = _make_mock_response(
            '{"action": "checkout", "time": "5:30 PM", "is_jibble": false, "jibble_first_name": null}'
        )

        result = parser.parse("Checkout 5:30 PM")

        assert result == ParseResult("checkout", "5:30 PM", False, None)


class TestLLMParserJibble:
    def test_jibble_in(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.return_value = _make_mock_response(
            '{"action": "checkin", "time": null, "is_jibble": true, "jibble_first_name": "Haseeb"}'
        )

        result = parser.parse("Haseeb jibbled in via Web (Chrome)")

        assert result == ParseResult("checkin", None, True, "Haseeb")


class TestLLMParserSkip:
    def test_random_message(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.return_value = _make_mock_response(
            '{"action": "skip", "time": null, "is_jibble": false, "jibble_first_name": null}'
        )

        result = parser.parse("Good morning everyone!")

        assert result.action == "skip"

    def test_zapier_message(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.return_value = _make_mock_response(
            '{"action": "skip", "time": null, "is_jibble": false, "jibble_first_name": null}'
        )

        result = parser.parse("Good Afternoon Team! Sent by Zapier")

        assert result.action == "skip"


class TestLLMParserErrors:
    def test_api_failure_returns_none(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.side_effect = Exception("API error")

        result = parser.parse("Check in 10:00 am")

        assert result is None

    def test_invalid_json_returns_none(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.return_value = _make_mock_response(
            "not valid json at all"
        )

        result = parser.parse("Check in 10:00 am")

        assert result is None

    def test_invalid_action_defaults_to_skip(self):
        parser = LLMParser(api_key="test", model="test-model")
        parser.client = MagicMock()
        parser.client.chat.completions.create.return_value = _make_mock_response(
            '{"action": "unknown", "time": null, "is_jibble": false, "jibble_first_name": null}'
        )

        result = parser.parse("some message")

        assert result.action == "skip"


class TestLLMParserUnconfigured:
    @patch("llm_parser.get_llm_parser", return_value=None)
    def test_unconfigured_returns_none(self, mock_get):
        from llm_parser import llm_parse_message

        result = llm_parse_message("Check in 10:00 am")

        assert result is None
