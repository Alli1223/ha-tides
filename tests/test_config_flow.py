"""Tests for the config/options flow schemas.

Building a vol.Schema with NumberSelector fields exercises Home Assistant's
own selector validation immediately (NumberSelector.__init__ runs its
CONFIG_SCHEMA on construction, not lazily) - HA rejects, for example, a
`step` smaller than 1e-3. That's a real bug this project shipped once
(latitude/longitude used step=0.0001) and it broke the config flow
entirely: every attempt to add the integration raised before the form
could even be shown. These tests build the schemas the same way the flow
does, so a similarly-invalid selector config fails fast here instead of
only in a user's live Home Assistant instance.
"""

from __future__ import annotations

import pytest


class _FakeConfig:
    latitude = 51.5
    longitude = -0.13


class _FakeHass:
    config = _FakeConfig()


def test_location_schema_builds_without_error():
    from custom_components.tides.config_flow import _location_schema

    schema = _location_schema(_FakeHass(), {})
    result = schema({"name": "Home", "latitude": 51.5, "longitude": -0.13})
    assert result["latitude"] == 51.5
    assert result["longitude"] == -0.13


def test_location_schema_accepts_fractional_minute_precision():
    # 0.001 degrees is ~111m - the finest step HA's NumberSelector allows.
    from custom_components.tides.config_flow import _location_schema

    schema = _location_schema(_FakeHass(), {})
    result = schema({"name": "Home", "latitude": 50.801, "longitude": -1.101})
    assert result["latitude"] == 50.801


def test_options_schema_builds_without_error():
    from custom_components.tides.config_flow import _options_schema

    schema = _options_schema({})
    result = schema({"tidal_range": 2.0, "calibration_offset": 30})
    assert result["tidal_range"] == 2.0
    assert result["calibration_offset"] == 30


@pytest.mark.parametrize("bad_step", [0.0, 0.0001, 1e-4, -1])
def test_number_selector_rejects_too_small_a_step(bad_step):
    # Guards the underlying assumption the two tests above rely on: HA's
    # NumberSelector really does reject sub-millidegree steps, so a schema
    # that builds cleanly is meaningful, not just an accident of mocking.
    from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig

    with pytest.raises(Exception):
        NumberSelector(NumberSelectorConfig(min=-90, max=90, step=bad_step))
