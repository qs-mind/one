"""Today's date in Cairo, which the core gives every agent."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo("Africa/Cairo")


def today(now: datetime) -> date:
    """The day in Cairo at the moment `now` (an aware datetime)."""
    return now.astimezone(CAIRO).date()


def today_line(now: datetime) -> str:
    """The instruction line that gives every agent today's date, from the core's clock."""
    day = today(now)
    return (
        f"Today is {day.isoformat()} ({day.strftime('%A')}), Cairo time. A date you write "
        "(a letter's date, «today») is this one, never another."
    )
