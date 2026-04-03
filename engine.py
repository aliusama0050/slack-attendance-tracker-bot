import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from duration import calculate_duration
from msg_parser import parse_message
from resolver import SlackUserResolver
from sheets import GoogleSheetsClient

logger = logging.getLogger(__name__)

KARACHI = ZoneInfo("Asia/Karachi")


def get_event_time(event: dict) -> str:
    """Convert Slack event timestamp to 'H:MM am/pm' in Asia/Karachi timezone."""
    ts = float(event.get("ts", 0))
    dt = datetime.fromtimestamp(ts, tz=KARACHI)
    return dt.strftime("%I:%M %p").lstrip("0")


def process_attendance(
    event: dict,
    resolver: SlackUserResolver,
    sheets: GoogleSheetsClient,
) -> None:
    """Core decision engine for processing attendance events.

    Called as a background task from the FastAPI endpoint.
    """
    text = event.get("text", "")
    user_id = event.get("user")

    # 1. Parse message
    result = parse_message(text)
    if result.action == "skip":
        logger.debug("Skipping message: %s", text[:80])
        return

    # 2. Resolve name
    if result.is_jibble:
        name = resolver.resolve_jibble_name(result.jibble_first_name)
        logger.info("Jibble message from '%s' resolved to '%s'",
                     result.jibble_first_name, name)
    else:
        if not user_id:
            logger.warning("No user_id in event, skipping")
            return
        name = resolver.resolve_user_id(user_id)

    if not name:
        logger.warning("Could not resolve user name, skipping. user_id=%s, jibble=%s",
                        user_id, result.jibble_first_name)
        return

    # 3. Determine time
    time_str = result.time_str if result.time_str else get_event_time(event)

    # 4. Determine dates
    now = datetime.now(KARACHI)
    today = now.strftime("%Y-%m-%d")

    # 5. Decision logic
    if result.action == "checkin":
        # Auto-close any recent unclosed shift (up to 7 days back)
        for days_ago in range(1, 8):
            past_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            past_row = sheets.find_row(name, past_date)
            if past_row and not past_row["checkout"]:
                sheets.update_row(name, past_row["row_number"], "Missed", "Missed")
                logger.warning("Auto-closed missed checkout for %s on %s", name, past_date)
                break

        existing = sheets.find_row(name, today)
        if existing:
            if existing["checkin"] in ("N/A", ""):
                # A checkout-only row exists — fill in the real check-in time
                sheets.update_checkin(name, existing["row_number"], time_str)
                if existing["checkout"]:
                    duration = calculate_duration(time_str, existing["checkout"])
                    sheets.update_row(name, existing["row_number"],
                                      existing["checkout"], duration)
                logger.info("Updated checkout-only row with check-in for %s: %s",
                             name, time_str)
            else:
                logger.info("Duplicate check-in for %s on %s, ignoring", name, today)
            return
        sheets.append_row(name, today, time_str, "", "")
        logger.info("Created check-in row: %s | %s | %s", name, today, time_str)

    elif result.action == "checkout":
        # Try today's row first
        today_row = sheets.find_row(name, today)
        if today_row:
            duration = calculate_duration(today_row["checkin"], time_str)
            sheets.update_row(name, today_row["row_number"], time_str, duration)
            logger.info("Updated today's row for %s: checkout=%s, duration=%s",
                         name, time_str, duration)
            return

        # Try recent days for unclosed row (overnight / multi-day shift, up to 7 days)
        for days_ago in range(1, 8):
            past_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            past_row = sheets.find_row(name, past_date)
            if past_row and not past_row["checkout"]:
                duration = calculate_duration(past_row["checkin"], time_str)
                sheets.update_row(name, past_row["row_number"], time_str, duration)
                logger.info("Updated row for %s on %s: checkout=%s, duration=%s",
                             name, past_date, time_str, duration)
                return

        # No row found — create with N/A check-in
        sheets.append_row(name, today, "N/A", time_str, "N/A")
        logger.info("Created checkout-only row for %s: N/A check-in, checkout=%s",
                     name, time_str)
