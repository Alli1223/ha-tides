"""Tests for the self-contained astronomical tide model.

Loaded directly from its file path (rather than via
``custom_components.tides.tide_math``) so these tests only need the
standard library, not a full Home Assistant install: importing the
``tides`` package normally would execute its ``__init__.py``, which
depends on ``homeassistant``.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "tides"
    / "tide_math.py"
)
spec = importlib.util.spec_from_file_location("tide_math", MODULE_PATH)
tide_math = importlib.util.module_from_spec(spec)
sys.modules["tide_math"] = tide_math
spec.loader.exec_module(tide_math)

# A real-ish coastal location (Portsmouth, UK) used across several tests.
LAT, LON = 50.8, -1.1


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_julian_day_j2000_epoch():
    assert tide_math.julian_day(_utc(2000, 1, 1, 12, 0, 0)) == 2451545.0


def test_julian_day_requires_aware_datetime():
    import pytest

    with pytest.raises(ValueError):
        tide_math.julian_day(datetime(2000, 1, 1))


def test_sun_declination_near_solstices():
    _, june_dec, _ = tide_math._sun_position(
        (tide_math.julian_day(_utc(2026, 6, 21, 12)) - 2451545.0) / 36525.0
    )
    _, dec_dec, _ = tide_math._sun_position(
        (tide_math.julian_day(_utc(2026, 12, 21, 12)) - 2451545.0) / 36525.0
    )
    assert 20 < june_dec < 23.6
    assert -23.6 < dec_dec < -20


def test_sun_declination_near_equinox_is_small():
    _, dec, _ = tide_math._sun_position(
        (tide_math.julian_day(_utc(2026, 3, 20, 12)) - 2451545.0) / 36525.0
    )
    assert abs(dec) < 2


def test_tide_height_stays_within_generous_bounds():
    amplitude = 2.0
    start = _utc(2026, 1, 1)
    for point_time, height in tide_math.sample_curve(
        start, start + timedelta(days=10), LAT, LON, amplitude, step=timedelta(hours=1)
    ):
        assert -amplitude <= height <= amplitude


def test_extrema_alternate_and_are_semidiurnal():
    start = _utc(2026, 3, 1)
    end = start + timedelta(days=5)
    events = tide_math.find_extrema(start, end, LAT, LON, amplitude=1.5)

    assert len(events) > 5

    kinds = [e.kind for e in events]
    for a, b in zip(kinds, kinds[1:]):
        assert a != b, "consecutive tide events should alternate high/low"

    # With diurnal inequality, consecutive same-kind tides (e.g. low -> low)
    # are *not* evenly spaced within a day (one is a stronger tide than the
    # other) - only after a full lunar day (4 events later: low, high, low,
    # high) should the same tide recur, ~24h50m on.
    lunar_day_gaps = [
        (b.time - a.time) for a, b in zip(events, events[4:]) if a.kind == b.kind
    ]
    assert lunar_day_gaps
    for gap in lunar_day_gaps:
        hours = gap.total_seconds() / 3600
        assert 22 < hours < 27, f"expected ~24h50m per lunar day, got {hours}h"


def test_current_state_after_high_is_falling_and_after_low_is_rising():
    start = _utc(2026, 3, 1)
    end = start + timedelta(days=2)
    events = tide_math.find_extrema(start, end, LAT, LON, amplitude=1.5)

    checked_high = checked_low = False
    for event in events:
        moment = event.time + timedelta(minutes=5)
        state = tide_math.current_state(moment, LAT, LON, amplitude=1.5)
        if event.kind == "high":
            assert state == "falling"
            checked_high = True
        else:
            assert state == "rising"
            checked_low = True
    assert checked_high and checked_low


def test_calibration_offset_shifts_events_later():
    start = _utc(2026, 3, 1)
    end = start + timedelta(days=3)
    baseline = tide_math.find_extrema(start, end, LAT, LON, amplitude=1.5)
    shifted = tide_math.find_extrema(
        start, end, LAT, LON, amplitude=1.5, calibration_minutes=60
    )

    assert len(baseline) == len(shifted)
    for base_event, shifted_event in zip(baseline, shifted):
        delta_minutes = (shifted_event.time - base_event.time).total_seconds() / 60
        assert 55 < delta_minutes < 65
