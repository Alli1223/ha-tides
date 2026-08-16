"""Data update coordinator for the Tides integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from astral import Observer
from astral.sun import sun as astral_sun

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import tide_math
from .const import (
    CONF_CALIBRATION_OFFSET,
    CONF_TIDAL_RANGE,
    DEFAULT_CALIBRATION_OFFSET,
    DEFAULT_TIDAL_RANGE,
    UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

# How far back/forward the sampled curve and tide-event search extends
# around "now". Wide enough that the card has room to show a day either
# side of now if it wants to.
_WINDOW_BACK = timedelta(hours=12)
_WINDOW_FORWARD = timedelta(hours=42)
_CURVE_STEP = timedelta(minutes=15)


@dataclass(frozen=True)
class SunEvent:
    """A sunrise or sunset."""

    kind: str  # "sunrise" | "sunset"
    time: datetime


@dataclass(frozen=True)
class TidesData:
    """Snapshot of tide predictions for a location, ready for entities/cards."""

    state: str  # "rising" | "falling"
    height: float
    amplitude: float
    generated_at: datetime
    previous_event: tide_math.TideEvent | None
    next_event: tide_math.TideEvent
    following_event: tide_math.TideEvent | None
    sun_events: list[SunEvent]
    curve: list[tuple[datetime, float]]


def _sun_events(latitude: float, longitude: float, start: datetime, end: datetime) -> list[SunEvent]:
    """Sunrises/sunsets (as absolute UTC instants) overlapping [start, end]."""
    observer = Observer(latitude=latitude, longitude=longitude)
    events: list[SunEvent] = []
    day = start.date() - timedelta(days=1)
    last_day = end.date() + timedelta(days=1)
    while day <= last_day:
        try:
            times = astral_sun(observer, date=day, tzinfo=timezone.utc)
        except ValueError:
            # Polar day/night: no sunrise or sunset on this date.
            day += timedelta(days=1)
            continue
        for kind in ("sunrise", "sunset"):
            when = times[kind]
            if start <= when <= end:
                events.append(SunEvent(kind=kind, time=when))
        day += timedelta(days=1)
    events.sort(key=lambda e: e.time)
    return events


def _compute(
    latitude: float,
    longitude: float,
    amplitude: float,
    calibration_minutes: float,
) -> TidesData:
    """Run the (synchronous, CPU-bound) tide computation."""
    now = dt_util.utcnow()
    start = now - _WINDOW_BACK
    end = now + _WINDOW_FORWARD

    height = tide_math.tide_height(now, latitude, longitude, amplitude, calibration_minutes)
    state = tide_math.current_state(now, latitude, longitude, amplitude, calibration_minutes)
    events = tide_math.find_extrema(
        start, end, latitude, longitude, amplitude, calibration_minutes
    )
    curve = tide_math.sample_curve(
        start, end, latitude, longitude, amplitude, calibration_minutes, step=_CURVE_STEP
    )

    previous_event = next((e for e in reversed(events) if e.time <= now), None)
    upcoming = [e for e in events if e.time > now]
    next_event = upcoming[0] if upcoming else events[-1]
    following_event = upcoming[1] if len(upcoming) > 1 else None

    return TidesData(
        state=state,
        height=height,
        amplitude=amplitude,
        generated_at=now,
        previous_event=previous_event,
        next_event=next_event,
        following_event=following_event,
        sun_events=_sun_events(latitude, longitude, start, end),
        curve=curve,
    )


class TidesDataUpdateCoordinator(DataUpdateCoordinator[TidesData]):
    """Coordinator that periodically recomputes tide predictions."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"tides-{entry.entry_id}",
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self.entry = entry

    @property
    def latitude(self) -> float:
        return self.entry.data[CONF_LATITUDE]

    @property
    def longitude(self) -> float:
        return self.entry.data[CONF_LONGITUDE]

    @property
    def location_name(self) -> str:
        return self.entry.data.get(CONF_NAME, self.entry.title)

    @property
    def amplitude(self) -> float:
        return self.entry.options.get(CONF_TIDAL_RANGE, DEFAULT_TIDAL_RANGE)

    @property
    def calibration_minutes(self) -> float:
        return self.entry.options.get(CONF_CALIBRATION_OFFSET, DEFAULT_CALIBRATION_OFFSET)

    async def _async_update_data(self) -> TidesData:
        return await self.hass.async_add_executor_job(
            _compute,
            self.latitude,
            self.longitude,
            self.amplitude,
            self.calibration_minutes,
        )
