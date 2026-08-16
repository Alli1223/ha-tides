"""Self-contained astronomical tide prediction.

No external tide API or harmonic-constituent database is used. Instead this
module computes the "equilibrium tide" — the theoretical tide height implied
by the Sun and Moon's positions relative to a point on Earth's surface — from
low-precision solar/lunar position formulas (Meeus, *Astronomical
Algorithms*, truncated series).

This is a genuine, from-first-principles computation, but it is an
approximation: real tide times/heights also depend on local coastline shape,
seabed depth and ocean resonance, which cause a fixed lag ("establishment of
the port") relative to the equilibrium tide. A constant calibration offset
(``calibration_minutes``) is provided so a user who knows one local high-tide
time can shift the whole prediction to line up with reality.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

# Relative strength of the Sun's tide-raising force vs. the Moon's.
_SOLAR_LUNAR_RATIO = 0.4605

# Fixed theoretical bounds of the raw equilibrium-tide potential (see
# `_raw_tide_potential`), used to rescale it into a +/-amplitude/2 metre
# range without an expensive search over each update.
_RAW_MIN = -(1 + _SOLAR_LUNAR_RATIO)
_RAW_MAX = 2 * (1 + _SOLAR_LUNAR_RATIO)
_RAW_RANGE = _RAW_MAX - _RAW_MIN

_MOON_MEAN_DISTANCE_KM = 385000.56

TideKind = Literal["high", "low"]


@dataclass(frozen=True)
class TideEvent:
    """A predicted high or low tide."""

    time: datetime
    kind: TideKind
    height: float


def _norm_deg(value: float) -> float:
    """Normalize an angle in degrees to [0, 360)."""
    return value % 360.0


def julian_day(dt_utc: datetime) -> float:
    """Convert an aware UTC datetime to a Julian Day number."""
    if dt_utc.tzinfo is None:
        raise ValueError("dt_utc must be timezone-aware")
    dt_utc = dt_utc.astimezone(timezone.utc)

    year, month = dt_utc.year, dt_utc.month
    day = dt_utc.day + (
        dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    ) / 24
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + day
        + b
        - 1524.5
    )


def _mean_obliquity_deg(t: float) -> float:
    return 23.439291 - 0.0130042 * t - 0.00000016 * t**2


def _sun_position(t: float) -> tuple[float, float, float]:
    """Low-precision solar position.

    Returns (right_ascension_deg, declination_deg, distance_au).
    """
    l0 = _norm_deg(280.46646 + 36000.76983 * t + 0.0003032 * t**2)
    m = _norm_deg(357.52911 + 35999.05029 * t - 0.0001537 * t**2)
    e = 0.016708634 - 0.000042037 * t - 0.0000001267 * t**2

    m_rad = math.radians(m)
    c = (
        (1.914602 - 0.004817 * t - 0.000014 * t**2) * math.sin(m_rad)
        + (0.019993 - 0.000101 * t) * math.sin(2 * m_rad)
        + 0.000289 * math.sin(3 * m_rad)
    )
    true_long = l0 + c
    true_anom_rad = math.radians(m + c)
    distance_au = (1.000001018 * (1 - e**2)) / (1 + e * math.cos(true_anom_rad))

    omega = 125.04 - 1934.136 * t
    apparent_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    eps0 = _mean_obliquity_deg(t)
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))

    lam = math.radians(apparent_long)
    eps_rad = math.radians(eps)
    ra = math.degrees(math.atan2(math.cos(eps_rad) * math.sin(lam), math.cos(lam)))
    dec = math.degrees(math.asin(math.sin(eps_rad) * math.sin(lam)))
    return _norm_deg(ra), dec, distance_au


def _moon_position(t: float) -> tuple[float, float, float]:
    """Truncated low-precision lunar position.

    Returns (right_ascension_deg, declination_deg, distance_km).
    """
    lp = _norm_deg(218.3164477 + 481267.88123421 * t - 0.0015786 * t**2)
    d = _norm_deg(297.8501921 + 445267.1114034 * t - 0.0018819 * t**2)
    m = _norm_deg(357.5291092 + 35999.0502909 * t - 0.0001536 * t**2)
    mp = _norm_deg(134.9633964 + 477198.8675055 * t + 0.0087414 * t**2)
    f = _norm_deg(93.272095 + 483202.0175233 * t - 0.0036539 * t**2)

    d_r, m_r, mp_r, f_r = (math.radians(x) for x in (d, m, mp, f))

    longitude = lp + (
        6.288774 * math.sin(mp_r)
        - 1.274027 * math.sin(2 * d_r - mp_r)
        + 0.658314 * math.sin(2 * d_r)
        + 0.213618 * math.sin(2 * mp_r)
        - 0.185116 * math.sin(m_r)
        - 0.114332 * math.sin(2 * f_r)
        + 0.058793 * math.sin(2 * d_r - 2 * mp_r)
        + 0.057066 * math.sin(2 * d_r - m_r - mp_r)
        + 0.053322 * math.sin(2 * d_r + mp_r)
        + 0.045758 * math.sin(2 * d_r - m_r)
        - 0.040923 * math.sin(m_r - mp_r)
        - 0.03438 * math.sin(d_r)
        - 0.030383 * math.sin(m_r + mp_r)
    )

    latitude = (
        5.128122 * math.sin(f_r)
        + 0.280602 * math.sin(mp_r + f_r)
        + 0.277693 * math.sin(mp_r - f_r)
        + 0.173237 * math.sin(2 * d_r - f_r)
        + 0.055413 * math.sin(2 * d_r + f_r - mp_r)
        + 0.046271 * math.sin(2 * d_r - f_r - mp_r)
        + 0.032573 * math.sin(2 * d_r + f_r)
        + 0.017198 * math.sin(2 * mp_r + f_r)
        + 0.009266 * math.sin(2 * d_r + mp_r - f_r)
        + 0.008822 * math.sin(2 * d_r - mp_r - f_r)
    )

    distance_km = (
        _MOON_MEAN_DISTANCE_KM
        - 20905.355 * math.cos(mp_r)
        - 3699.111 * math.cos(2 * d_r - mp_r)
        - 2955.968 * math.cos(2 * d_r)
        - 569.925 * math.cos(2 * mp_r)
    )

    eps_rad = math.radians(_mean_obliquity_deg(t))
    lam = math.radians(_norm_deg(longitude))
    beta = math.radians(latitude)

    ra = math.degrees(
        math.atan2(
            math.sin(lam) * math.cos(eps_rad) - math.tan(beta) * math.sin(eps_rad),
            math.cos(lam),
        )
    )
    dec = math.degrees(
        math.asin(
            math.sin(beta) * math.cos(eps_rad)
            + math.cos(beta) * math.sin(eps_rad) * math.sin(lam)
        )
    )
    return _norm_deg(ra), dec, distance_km


def _greenwich_sidereal_time_deg(jd: float, t: float) -> float:
    gst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t**2
        - t**3 / 38710000
    )
    return _norm_deg(gst)


def _zenith_cos(lat_rad: float, dec_deg: float, hour_angle_deg: float) -> float:
    dec_rad = math.radians(dec_deg)
    h_rad = math.radians(hour_angle_deg)
    return math.sin(lat_rad) * math.sin(dec_rad) + math.cos(lat_rad) * math.cos(
        dec_rad
    ) * math.cos(h_rad)


def _raw_tide_potential(dt_utc: datetime, latitude: float, longitude: float) -> float:
    """The dimensionless equilibrium-tide potential at a place and time."""
    jd = julian_day(dt_utc)
    t = (jd - 2451545.0) / 36525.0
    gst = _greenwich_sidereal_time_deg(jd, t)
    lat_rad = math.radians(latitude)

    sun_ra, sun_dec, sun_dist_au = _sun_position(t)
    moon_ra, moon_dec, moon_dist_km = _moon_position(t)

    sun_h = gst + longitude - sun_ra
    moon_h = gst + longitude - moon_ra

    cos_z_sun = _zenith_cos(lat_rad, sun_dec, sun_h)
    cos_z_moon = _zenith_cos(lat_rad, moon_dec, moon_h)

    moon_term = (3 * cos_z_moon**2 - 1) * (_MOON_MEAN_DISTANCE_KM / moon_dist_km) ** 3
    sun_term = (
        _SOLAR_LUNAR_RATIO * (3 * cos_z_sun**2 - 1) * (1 / sun_dist_au) ** 3
    )
    return moon_term + sun_term


def tide_height(
    dt_utc: datetime,
    latitude: float,
    longitude: float,
    amplitude: float = 1.5,
    calibration_minutes: float = 0.0,
) -> float:
    """Predicted tide height in metres, relative to mean sea level.

    ``amplitude`` is the local crest-to-trough tidal range in metres.
    ``calibration_minutes`` shifts the whole prediction in time, to correct
    for the fixed lag real tides have relative to the equilibrium tide at a
    given coastline.
    """
    shifted = dt_utc - timedelta(minutes=calibration_minutes)
    raw = _raw_tide_potential(shifted, latitude, longitude)
    return amplitude * (raw - _RAW_MIN) / _RAW_RANGE - amplitude / 2


def sample_curve(
    start: datetime,
    end: datetime,
    latitude: float,
    longitude: float,
    amplitude: float = 1.5,
    calibration_minutes: float = 0.0,
    step: timedelta = timedelta(minutes=15),
) -> list[tuple[datetime, float]]:
    """Sample the tide curve between start and end at a fixed step."""
    points: list[tuple[datetime, float]] = []
    t = start
    while t <= end:
        points.append(
            (t, tide_height(t, latitude, longitude, amplitude, calibration_minutes))
        )
        t += step
    return points


def _refine_extremum(
    lower: datetime,
    upper: datetime,
    kind: TideKind,
    latitude: float,
    longitude: float,
    amplitude: float,
    calibration_minutes: float,
) -> TideEvent:
    """Golden-section search for the extremum time within (lower, upper)."""
    invphi = (math.sqrt(5) - 1) / 2

    def height_at(dt: datetime) -> float:
        h = tide_height(dt, latitude, longitude, amplitude, calibration_minutes)
        return h if kind == "high" else -h

    a, b = lower, upper
    span = b - a
    c = b - span * invphi
    d = a + span * invphi
    fc, fd = height_at(c), height_at(d)

    for _ in range(40):
        if (b - a) <= timedelta(seconds=30):
            break
        if fc > fd:
            b, d, fd = d, c, fc
            span = b - a
            c = b - span * invphi
            fc = height_at(c)
        else:
            a, c, fc = c, d, fd
            span = b - a
            d = a + span * invphi
            fd = height_at(d)

    best_time = c if fc > fd else d
    return TideEvent(
        time=best_time,
        kind=kind,
        height=tide_height(
            best_time, latitude, longitude, amplitude, calibration_minutes
        ),
    )


def find_extrema(
    start: datetime,
    end: datetime,
    latitude: float,
    longitude: float,
    amplitude: float = 1.5,
    calibration_minutes: float = 0.0,
    coarse_step: timedelta = timedelta(minutes=10),
) -> list[TideEvent]:
    """Find all high/low tide events between start and end."""
    # Pad the coarse scan so an extremum right at the edge of the window can
    # still be bracketed and refined correctly.
    pad = coarse_step * 3
    samples = sample_curve(
        start - pad,
        end + pad,
        latitude,
        longitude,
        amplitude,
        calibration_minutes,
        coarse_step,
    )

    events: list[TideEvent] = []
    for i in range(1, len(samples) - 1):
        prev_h, cur_h, next_h = samples[i - 1][1], samples[i][1], samples[i + 1][1]
        if cur_h >= prev_h and cur_h >= next_h:
            kind: TideKind = "high"
        elif cur_h <= prev_h and cur_h <= next_h:
            kind = "low"
        else:
            continue
        event = _refine_extremum(
            samples[i - 1][0],
            samples[i + 1][0],
            kind,
            latitude,
            longitude,
            amplitude,
            calibration_minutes,
        )
        if start <= event.time <= end:
            events.append(event)

    events.sort(key=lambda e: e.time)
    # De-duplicate events that the coarse scan may have bracketed twice.
    deduped: list[TideEvent] = []
    for event in events:
        if deduped and abs((event.time - deduped[-1].time).total_seconds()) < 60:
            continue
        deduped.append(event)
    return deduped


def current_state(
    dt_utc: datetime,
    latitude: float,
    longitude: float,
    amplitude: float = 1.5,
    calibration_minutes: float = 0.0,
) -> Literal["rising", "falling"]:
    """Whether the tide is currently rising or falling."""
    now_h = tide_height(dt_utc, latitude, longitude, amplitude, calibration_minutes)
    later_h = tide_height(
        dt_utc + timedelta(minutes=1),
        latitude,
        longitude,
        amplitude,
        calibration_minutes,
    )
    return "rising" if later_h >= now_h else "falling"
