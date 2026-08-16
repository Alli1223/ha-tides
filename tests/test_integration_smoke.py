"""Smoke tests against the real ``homeassistant`` package.

These catch import-path/API drift (wrong helper module, renamed selector,
etc.) that pure-math tests can't see, without needing a running Home
Assistant instance.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from homeassistant.util import dt as dt_util

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_manifest_matches_domain_const():
    from custom_components.tides.const import DOMAIN

    manifest = json.loads(
        (REPO_ROOT / "custom_components" / "tides" / "manifest.json").read_text()
    )
    assert manifest["domain"] == DOMAIN


def test_translations_mirror_strings():
    strings = json.loads(
        (REPO_ROOT / "custom_components" / "tides" / "strings.json").read_text()
    )
    translations = json.loads(
        (
            REPO_ROOT
            / "custom_components"
            / "tides"
            / "translations"
            / "en.json"
        ).read_text()
    )
    assert strings == translations


def test_platform_modules_import_cleanly():
    import custom_components.tides
    import custom_components.tides.config_flow
    import custom_components.tides.coordinator
    import custom_components.tides.sensor

    assert custom_components.tides.PLATFORMS


def test_compute_pipeline_end_to_end():
    from custom_components.tides.coordinator import _compute

    data = _compute(latitude=50.8, longitude=-1.1, amplitude=1.5, calibration_minutes=0)

    assert data.previous_event.time <= data.generated_at < data.next_event.time
    assert data.previous_event.kind != data.next_event.kind
    if data.following_event is not None:
        assert data.following_event.kind != data.next_event.kind
        assert data.next_event.time < data.following_event.time

    assert -1.5 <= data.height <= 1.5

    assert data.sun_events == sorted(data.sun_events, key=lambda e: e.time)
    assert all(e.kind in ("sunrise", "sunset") for e in data.sun_events)

    times = [t for t, _ in data.curve]
    assert times == sorted(times)
    assert len(data.curve) > 100


def test_dt_util_utcnow_is_aware():
    # Sanity-check the HA time helper the coordinator relies on.
    now = dt_util.utcnow()
    assert now.tzinfo is not None
    assert now - timedelta(minutes=1) < now
