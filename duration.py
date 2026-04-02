import datetime
import re


def normalize_time(raw: str) -> datetime.time | None:
    """Parse time strings like '8:10pm', '8:10 PM', '08:10 AM', '8:10'.
    Returns datetime.time or None if unparseable."""
    cleaned = raw.strip().upper()
    # Remove dots from a.m./p.m.
    cleaned = cleaned.replace(".", "")

    patterns = [
        "%I:%M%p",   # 8:10PM
        "%I:%M %p",  # 8:10 PM
        "%H:%M",     # 08:10 (24-hour)
    ]
    for fmt in patterns:
        try:
            return datetime.datetime.strptime(cleaned, fmt).time()
        except ValueError:
            continue
    return None


def calculate_duration(checkin_str: str, checkout_str: str) -> str:
    """Calculate duration between check-in and check-out times.

    Returns:
        'Xh Ym' format string
        'N/A' if checkin is N/A
        'Parse Error' if either time is unparseable
    """
    if checkin_str.strip().upper() == "N/A":
        return "N/A"

    checkin_time = normalize_time(checkin_str)
    checkout_time = normalize_time(checkout_str)

    if checkin_time is None or checkout_time is None:
        return "Parse Error"

    base_date = datetime.date(2000, 1, 1)
    checkin_dt = datetime.datetime.combine(base_date, checkin_time)
    checkout_dt = datetime.datetime.combine(base_date, checkout_time)

    delta = checkout_dt - checkin_dt
    # Handle overnight: if checkout is before checkin, add 24 hours
    if delta.total_seconds() < 0:
        delta += datetime.timedelta(hours=24)

    total_seconds = int(delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours}h {minutes}m"
