from calendar import monthrange
from datetime import date, timedelta

# Membership plan name -> number of months it spans.
MEMBERSHIP_DURATION_MONTHS = {
    "Monthly": 1,
    "Quarterly": 3,
    "Half-Yearly": 6,
    "Yearly": 12,
}


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def calculate_membership_end(start_date: date, membership: str) -> date:
    """Same day N months later, minus one day (e.g. Monthly: Jan 15 -> Feb 14)."""
    months = MEMBERSHIP_DURATION_MONTHS[membership]
    return add_months(start_date, months) - timedelta(days=1)
