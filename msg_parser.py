import re
from dataclasses import dataclass
from typing import Literal


@dataclass
class ParseResult:
    action: Literal["checkin", "checkout", "skip"]
    time_str: str | None
    is_jibble: bool
    jibble_first_name: str | None


# Patterns
_ZAPIER_RE = re.compile(r"sent by zapier", re.IGNORECASE)
_JIBBLE_RE = re.compile(r"(\w+)\s+jibbled\s+(in|out)\s+via", re.IGNORECASE)
_CHECKINOUT_RE = re.compile(
    r"check(?:ed)?\s*[-]?\s*(in|out)\s*[:\s]*(?:at\s*)?(\d{1,2}:\d{2}\s*[ap]\.?m\.?)?",
    re.IGNORECASE,
)


def parse_message(text: str) -> ParseResult:
    """Parse a Slack message and determine attendance action."""
    # 1. Zapier detection
    if _ZAPIER_RE.search(text):
        return ParseResult("skip", None, False, None)

    # 2. Jibble detection
    m = _JIBBLE_RE.search(text)
    if m:
        action = "checkin" if m.group(2).lower() == "in" else "checkout"
        return ParseResult(action, None, True, m.group(1))

    # 3. Manual check-in/out
    m = _CHECKINOUT_RE.search(text)
    if m:
        action = "checkin" if m.group(1).lower() == "in" else "checkout"
        time_str = m.group(2).strip() if m.group(2) else None
        return ParseResult(action, time_str, False, None)

    # 4. No match
    return ParseResult("skip", None, False, None)
