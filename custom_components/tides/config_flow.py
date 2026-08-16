"""Config flow for the Tides integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_CALIBRATION_OFFSET,
    CONF_TIDAL_RANGE,
    DEFAULT_CALIBRATION_OFFSET,
    DEFAULT_NAME,
    DEFAULT_TIDAL_RANGE,
    DOMAIN,
)


def _location_schema(hass, defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(
                CONF_LATITUDE,
                default=defaults.get(CONF_LATITUDE, hass.config.latitude),
            ): NumberSelector(
                NumberSelectorConfig(min=-90, max=90, step=0.001, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_LONGITUDE,
                default=defaults.get(CONF_LONGITUDE, hass.config.longitude),
            ): NumberSelector(
                NumberSelectorConfig(min=-180, max=180, step=0.001, mode=NumberSelectorMode.BOX)
            ),
        }
    )


class TidesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tides."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step: let the user set a name and location."""
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = (
                f"{round(user_input[CONF_LATITUDE], 3)}_"
                f"{round(user_input[CONF_LONGITUDE], 3)}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_location_schema(self.hass, {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TidesOptionsFlow:
        """Get the options flow for this handler."""
        return TidesOptionsFlow(config_entry)


def _options_schema(options: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_TIDAL_RANGE,
                default=options.get(CONF_TIDAL_RANGE, DEFAULT_TIDAL_RANGE),
            ): NumberSelector(
                NumberSelectorConfig(min=0.1, max=15, step=0.1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_CALIBRATION_OFFSET,
                default=options.get(CONF_CALIBRATION_OFFSET, DEFAULT_CALIBRATION_OFFSET),
            ): NumberSelector(
                NumberSelectorConfig(min=-720, max=720, step=5, mode=NumberSelectorMode.BOX)
            ),
        }
    )


class TidesOptionsFlow(config_entries.OptionsFlow):
    """Handle options for the Tides integration (amplitude and calibration)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the tuning options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init", data_schema=_options_schema(self._config_entry.options)
        )
