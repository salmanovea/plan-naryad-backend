"""Folding Raport's UTC datetimes to Moscow calendar days."""

import os
import time
from datetime import date

import pytest

from src.services.sync.service import _as_date


@pytest.fixture()
def moscow_tz():
    """A deliberately hostile process clock: UTC, like an image DevOps built."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    yield
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


def test_fact_entered_after_moscow_midnight_lands_on_its_moscow_day(moscow_tz):
    # Entered 04.09 00:30 MSK → serialized by Raport as 03.09 21:30 UTC.
    assert _as_date("2026-09-03T21:30:00Z") == date(2026, 9, 4)


def test_fact_entered_in_the_moscow_evening_stays_on_its_day(moscow_tz):
    # Entered 03.09 21:00 MSK → 18:00 UTC — no midnight crossing.
    assert _as_date("2026-09-03T18:00:00Z") == date(2026, 9, 3)


def test_explicit_moscow_offset_is_taken_as_is(moscow_tz):
    assert _as_date("2026-09-04T00:30:00+03:00") == date(2026, 9, 4)


def test_plain_date_passes_through(moscow_tz):
    assert _as_date("2026-09-03") == date(2026, 9, 3)


def test_naive_datetime_is_taken_at_face_value(moscow_tz):
    assert _as_date("2026-09-03T10:00:00") == date(2026, 9, 3)


def test_garbage_and_empty_yield_none(moscow_tz):
    assert _as_date("not-a-date") is None
    assert _as_date("") is None
    assert _as_date(None) is None
