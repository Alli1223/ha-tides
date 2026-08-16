"""Tests for the Lovelace card asset and its registration."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CARD_JS = REPO_ROOT / "custom_components" / "tides" / "www" / "tides-card.js"


def test_card_js_exists():
    assert CARD_JS.is_file()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_card_js_has_valid_syntax():
    result = subprocess.run(
        ["node", "--check", str(CARD_JS)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_static_url_matches_domain():
    from custom_components.tides import _CARD_URL
    from custom_components.tides.const import DOMAIN

    assert _CARD_URL == f"/{DOMAIN}/tides-card.js"


def test_card_registers_custom_elements():
    source = CARD_JS.read_text()
    assert 'customElements.define("tides-card"' in source
    assert 'customElements.define("tides-card-editor"' in source
    assert "window.customCards" in source
