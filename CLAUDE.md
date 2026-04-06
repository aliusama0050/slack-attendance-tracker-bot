# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Genifem Attendance is a FastAPI service that listens to Slack messages (via the Events API) and automatically records employee check-in/check-out times to a Google Sheet. It handles three message formats:
- **Manual** messages like "check in 10:47 am" or "checkout: 5:30 PM"
- **Jibble bot** messages like "Haseeb jibbled in via Web (Chrome)"
- **Zapier** messages are explicitly skipped

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server locally
python main.py                    # starts uvicorn on port 8001

# Run all tests
pytest

# Run a single test file
pytest tests/test_parser.py

# Run a specific test
pytest tests/test_parser.py::TestParseCheckin::test_check_in_with_time
```

## Architecture

The request pipeline flows as: `main.py → engine.py → (llm_parser.py / msg_parser.py + resolver.py + sheets.py + duration.py)`

- **main.py** — FastAPI app with `/slack/events` endpoint. Handles Slack signature verification, rate limiting, event deduplication, and channel filtering. Dispatches to `process_attendance` as a background task. Also handles `message_changed` events (edited messages) with `is_edit=True`.
- **engine.py** — Core decision logic. Orchestrates parsing → name resolution → sheet lookup/write. Handles check-in (new row), check-out (update today or yesterday's row for overnight shifts), checkout-only (N/A check-in), and edited message overwrites via `is_edit` flag. Auto-closes all unclosed rows (up to 7 days) on check-in. Guards against duplicate checkouts.
- **llm_parser.py** — LLM-based message parser using Groq Cloud API. Tries to parse messages intelligently; returns `None` on failure so engine falls back to regex. Configured via `GROQ_API_KEY` (disabled when empty).
- **msg_parser.py** — Regex-based message classifier (fallback). Returns a `ParseResult` dataclass with action (`checkin`/`checkout`/`skip`), optional time string, and Jibble metadata.
- **resolver.py** — `SlackUserResolver` maps Slack user IDs and Jibble first names to canonical display names. Caches workspace user list for 1 hour.
- **sheets.py** — `GoogleSheetsClient` wraps gspread. Each person gets their own worksheet tab. Columns: A=Date, B=Check-In, C=Check-Out, D=Duration. Has retry logic for Google API rate limits (429s).
- **duration.py** — Calculates time duration between check-in/check-out strings, handles overnight shifts. Also exports `normalize_time` for time comparison.
- **config.py** — Pydantic Settings loaded from `.env`. See `.env.example` for required variables.
- **api/index.py** — Vercel serverless entry point; re-exports the FastAPI app.

## Deployment

Two deployment targets:
- **EC2/VPS**: Uses `genifem-attendance.service` (systemd) + `nginx.conf` as reverse proxy
- **Vercel**: Uses `api/index.py` entry point + `vercel.json` routing config

## Key Details

- All times are in **Asia/Karachi** timezone
- `GOOGLE_SERVICE_ACCOUNT_JSON` can be either a file path (EC2) or raw JSON string (Vercel)
- Slack events are deduplicated via `event_id` with a 5-minute TTL cache
- The service only processes messages from the channel specified by `SLACK_CHANNEL_ID` (if set)
- Edited Slack messages (`message_changed` subtype) are re-processed with `is_edit=True`, allowing overwrites of existing check-in/check-out times
- Duplicate checkouts are ignored unless the message is an edit
- Checkout-only rows from overnight shifts are not merged with next-day check-ins (time comparison detects different shifts)
- `GROQ_API_KEY` enables LLM-based parsing via Groq Cloud; when empty, the service uses regex parsing only
