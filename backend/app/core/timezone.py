"""
Indian Standard Time (IST) Timezone and DateTime Engine.

All financial aging calculations, daily credit quotas, automation cycles,
reminder dispatch schedules, and audit log timestamps across the system
are strictly anchored to Indian Standard Time (Asia/Kolkata, UTC+05:30).
"""

from datetime import datetime, date, timezone, timedelta
from typing import Optional

# Indian Standard Time is UTC + 5 hours 30 minutes
IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET, name="IST")


def ist_now() -> datetime:
    """Returns the current aware datetime in Indian Standard Time (IST)."""
    return datetime.now(IST)


def ist_naive_now() -> datetime:
    """
    Returns the current datetime in Indian Standard Time (IST) as a naive datetime
    suitable for database TIMESTAMP columns without ambiguous timezone shifts.
    """
    return ist_now().replace(tzinfo=None)


def ist_today() -> date:
    """Returns the current calendar date in Indian Standard Time (IST)."""
    return ist_now().date()


def ist_start_of_day(target_date: Optional[date] = None) -> datetime:
    """Returns 00:00:00 (midnight) start of the day in IST as a naive datetime."""
    d = target_date or ist_today()
    return datetime.combine(d, datetime.min.time())


def ist_end_of_day(target_date: Optional[date] = None) -> datetime:
    """Returns 23:59:59.999999 end of the day in IST as a naive datetime."""
    d = target_date or ist_today()
    return datetime.combine(d, datetime.max.time())


def to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Converts any datetime (aware or naive) into an aware datetime localized to IST.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def format_ist_iso(dt: Optional[datetime]) -> Optional[str]:
    """Formats a datetime into standard ISO 8601 with '+05:30' IST offset."""
    if dt is None:
        return None
    return to_ist(dt).isoformat()
