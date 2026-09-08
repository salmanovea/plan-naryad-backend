"""Business clock of the service: all today and now are Moscow time.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.config.settings import app_config


def business_tz() -> ZoneInfo:
    return ZoneInfo(app_config.app_timezone)


def business_now() -> datetime:
    """Moscow wall-clock now, naive — the scale the DateTime columns store."""
    return datetime.now(business_tz()).replace(tzinfo=None)


def business_today() -> date:
    return datetime.now(business_tz()).date()
