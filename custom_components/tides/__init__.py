"""The Tides integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .coordinator import TidesDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

_CARD_URL = f"/{DOMAIN}/tides-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Lovelace card JS once, regardless of entry count."""
    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("frontend_registered"):
        integration = await async_get_integration(hass, DOMAIN)
        card_path = Path(__file__).parent / "www" / "tides-card.js"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARD_URL, str(card_path), cache_headers=False)]
        )
        # Cache-bust on integration updates so browsers pick up card changes.
        add_extra_js_url(hass, f"{_CARD_URL}?v={integration.version}")
        hass.data[DOMAIN]["frontend_registered"] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tides from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = TidesDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
