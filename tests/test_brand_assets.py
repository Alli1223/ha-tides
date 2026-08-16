"""Tests for the local brand icon assets."""

from __future__ import annotations

import struct
from pathlib import Path

BRAND_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "tides" / "brand"


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_brand_assets_exist_at_expected_sizes():
    expected = {
        "icon.png": (256, 256),
        "icon@2x.png": (512, 512),
        "logo.png": (256, 256),
        "logo@2x.png": (512, 512),
    }
    for name, size in expected.items():
        path = BRAND_DIR / name
        assert path.is_file(), f"missing {path}"
        assert _png_dimensions(path) == size


def test_icon_svg_source_exists():
    svg = BRAND_DIR.parent / "icon.svg"
    assert svg.is_file()
    assert "<svg" in svg.read_text()
