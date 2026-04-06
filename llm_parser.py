import json
import logging

from groq import Groq

from msg_parser import ParseResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an attendance message parser. Analyze the Slack message and extract:
1. action: "checkin", "checkout", or "skip"
2. time: extracted time string (e.g. "10:47 am", "5:30 PM") or null if not mentioned
3. is_jibble: true if this is a Jibble bot message
4. jibble_first_name: the first name from Jibble messages, or null

Rules:
- "check in", "checked in", "jibbled in", starting work, arriving → checkin
- "check out", "checked out", "jibbled out", leaving, signing off, done for today → checkout
- Messages containing "sent by zapier" → skip
- Random chat, greetings without attendance intent, reminders → skip
- Extract time exactly as written in the message; return null if no time mentioned
- For Jibble messages ("Name jibbled in/out via ..."), set is_jibble true and extract first name

Respond ONLY with valid JSON:
{"action": "checkin"|"checkout"|"skip", "time": "..."|null, "is_jibble": true|false, "jibble_first_name": "..."|null}"""


class LLMParser:
    """Attendance message parser using Groq Cloud LLM."""

    def __init__(self, api_key: str, model: str):
        self.client = Groq(api_key=api_key)
        self.model = model

    def parse(self, text: str) -> ParseResult | None:
        """Parse message using Groq LLM. Returns ParseResult or None on failure."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0,
                max_tokens=150,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            data = json.loads(content)

            action = data.get("action", "skip")
            if action not in ("checkin", "checkout", "skip"):
                action = "skip"

            return ParseResult(
                action=action,
                time_str=data.get("time"),
                is_jibble=bool(data.get("is_jibble", False)),
                jibble_first_name=data.get("jibble_first_name"),
            )
        except Exception:
            logger.exception("LLM parsing failed for message: %s", text[:100])
            return None


# Module-level singleton, initialized lazily
_parser: LLMParser | None = None


def get_llm_parser() -> LLMParser | None:
    """Get the LLM parser singleton. Returns None if Groq is not configured."""
    global _parser
    if _parser is not None:
        return _parser

    from config import settings

    if not settings.groq_api_key:
        return None

    _parser = LLMParser(api_key=settings.groq_api_key, model=settings.groq_model)
    return _parser


def llm_parse_message(text: str) -> ParseResult | None:
    """Parse with LLM. Returns None if unconfigured or on failure."""
    parser = get_llm_parser()
    if parser is None:
        return None
    return parser.parse(text)
