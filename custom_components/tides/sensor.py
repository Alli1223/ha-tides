"""Sensor platform for the Tides integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TidesDataUpdateCoordinator, TidesData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Tides sensor from a config entry."""
    coordinator: TidesDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TidesSensor(coordinator)])


def _event_dict(event) -> dict | None:
    if event is None:
        return None
    return {
        "time": event.time.isoformat(),
        "kind": event.kind,
        "height": round(event.height, 3),
    }


class TidesSensor(CoordinatorEntity[TidesDataUpdateCoordinator], SensorEntity):
    """Represents the current tide state for a location."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:waves"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["rising", "falling"]
    _attr_translation_key = "tide"
    # The sampled wave curve is large and changes every update; recording it
    # in history is neither useful nor cheap, so keep it out of the recorder.
    _unrecorded_attributes = frozenset({"curve", "sun_events"})

    def __init__(self, coordinator: TidesDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_tide"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.location_name,
            manufacturer="Tides (local astronomical model)",
            model="Equilibrium tide predictor",
        )

    @property
    def native_value(self) -> str:
        return self.coordinator.data.state

    @property
    def extra_state_attributes(self) -> dict:
        data: TidesData = self.coordinator.data

        high_event = low_event = None
        for event in (data.next_event, data.following_event):
            if event is None:
                continue
            if event.kind == "high" and high_event is None:
                high_event = event
            elif event.kind == "low" and low_event is None:
                low_event = event

        now = data.generated_at
        next_sunrise = next(
            (e.time for e in data.sun_events if e.kind == "sunrise" and e.time >= now),
            None,
        )
        next_sunset = next(
            (e.time for e in data.sun_events if e.kind == "sunset" and e.time >= now),
            None,
        )

        return {
            "height_m": round(data.height, 3),
            "tidal_range_m": data.amplitude,
            "next_high": _event_dict(high_event),
            "next_low": _event_dict(low_event),
            "previous_event": _event_dict(data.previous_event),
            "next_sunrise": next_sunrise.isoformat() if next_sunrise else None,
            "next_sunset": next_sunset.isoformat() if next_sunset else None,
            "sun_events": [
                {"kind": e.kind, "time": e.time.isoformat()} for e in data.sun_events
            ],
            "curve": [
                [point_time.isoformat(), round(height, 3)]
                for point_time, height in data.curve
            ],
        }
