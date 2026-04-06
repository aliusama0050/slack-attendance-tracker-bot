"""Live test of Groq LLM parser against real Slack messages."""

import sys
sys.path.insert(0, ".")

from config import settings
from llm_parser import LLMParser

parser = LLMParser(api_key=settings.groq_api_key, model=settings.groq_model)

# Real messages from the Slack channel
messages = [
    # Standard check-ins
    "check in :  8:13 am",
    "Check in 2:01 pm",
    "Check in: 7:20 pm",
    "Check in: 9:59 am",
    "check in : 8:35 am",
    "Check in: 9:08 am",

    # Standard checkouts
    "Checkout: 11:03 pm",
    "check out: 11:34pm",
    "Checkout: 11:51 pm",
    "check out: 12:19am",
    "check out: 12:41am",
    "Check out: 11:30 Pm",

    # Jibble messages
    "Haseeb jibbled in via Web (Chrome)",
    "Haseeb jibbled out via Web (Chrome)",

    # Zapier (should skip)
    "Good Afternoon Team! Please don't forget to add you Check-in & Check- out Time. \n\nSent by Zapier",

    # Random chat (should skip)
    "Good morning everyone!",
    "test",
    "",

    # Edge cases — messages the regex can't handle well
    "1 April\nCheck in 2:01 pm",
    "2 Apr\nCheck in 1:55 pm",
    "6 April \nCheck in 1:58 pm",
    "Checkout: 11:57 pm",  # was edited
    "I'm starting my shift now",
    "leaving for the day",
    "done for today, signing off at 6pm",
]

print(f"Model: {settings.groq_model}\n")
print(f"{'Message':<60} {'Action':<10} {'Time':<12} {'Jibble':<8} {'Name'}")
print("-" * 110)

for msg in messages:
    display = msg.replace("\n", "\\n")[:55]
    result = parser.parse(msg)
    if result is None:
        print(f"{display:<60} {'ERROR':<10}")
    else:
        name = result.jibble_first_name or ""
        time = result.time_str or ""
        jibble = "Yes" if result.is_jibble else ""
        print(f"{display:<60} {result.action:<10} {time:<12} {jibble:<8} {name}")
