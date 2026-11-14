"""Offline Swiss Ephemeris / Moshier natal positions, explicitly Lahiri sidereal.

Moshier is Swiss Ephemeris's analytical ephemeris, NOT a JPL kernel. It is
requested explicitly and returned flags are checked, so a library fallback
cannot silently change the source. The optional pyswisseph package has its own
licensing requirements; see vedic-requirements.txt before enabling a service.
"""
from __future__ import annotations

import math
import re
from threading import RLock

from .ephemeris import birth_utc

BACKEND = "swisseph-moshier"
SOURCE = "https://www.astro.com/swisseph/swephprg.htm"
_LOCK = RLock()


class VedicEphemerisUnavailable(Exception):
    pass


def _library():
    try:
        import swisseph
    except ImportError:
        raise VedicEphemerisUnavailable("pyswisseph is not provisioned") from None
    return swisseph


def backend_info():
    try:
        swe = _library()
        return {"backend": BACKEND, "status": "computed", "version": swe.version}
    except VedicEphemerisUnavailable:
        return {"backend": BACKEND, "status": "unavailable"}


def natal_positions(birth_input):
    """Return validated sidereal longitudes and an optional sidereal ascendant.

    Civil time is resolved by IANA rules, rejecting missing/ambiguous/nonexistent
    times. Calls that modify Swiss sidereal configuration share this lock.
    """
    if not isinstance(birth_input.birth_datetime, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{1,2}:[0-9]{2}", birth_input.birth_datetime.strip()):
        raise ValueError("An explicit birth time is required")
    utc = birth_utc(birth_input)  # validate before requesting a backend
    if (birth_input.latitude is None) != (birth_input.longitude is None):
        raise ValueError("Both birth coordinates are required")
    if birth_input.latitude is not None:
        lat, lon = birth_input.latitude, birth_input.longitude
        if (isinstance(lat, bool) or isinstance(lon, bool)
                or not isinstance(lat, (float, int)) or not isinstance(lon, (float, int))
                or not math.isfinite(lat) or not math.isfinite(lon)
                or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            raise ValueError("Invalid birth coordinates")
    swe = _library()
    with _LOCK:
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        _, jd_ut = swe.utc_to_jd(utc.year, utc.month, utc.day, utc.hour,
                                 utc.minute, utc.second + utc.microsecond / 1e6,
                                 swe.GREG_CAL)
        flags = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
        bodies = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS,
                  "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER,
                  "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
        rows = []
        for name, body in bodies.items():
            values, returned = swe.calc_ut(jd_ut, body, flags)
            if (returned & (swe.FLG_JPLEPH | swe.FLG_SWIEPH | swe.FLG_MOSEPH)) != swe.FLG_MOSEPH:
                raise VedicEphemerisUnavailable("Unexpected ephemeris source")
            if not returned & swe.FLG_SIDEREAL:
                raise VedicEphemerisUnavailable("Sidereal calculation was not honored")
            longitude, speed = float(values[0]), float(values[3])
            if not math.isfinite(longitude) or not 0 <= longitude < 360 or not math.isfinite(speed):
                raise VedicEphemerisUnavailable("Invalid ephemeris values")
            rows.append({"name": name, "longitude": longitude, "speed": speed})
        node = rows[-1]
        rows.append({"name": "Ketu", "longitude": (node["longitude"] + 180) % 360,
                     "speed": node["speed"]})
        ascendant = None
        if birth_input.has_location and abs(birth_input.latitude) < 89.99:
            _, angles = swe.houses_ex(jd_ut, birth_input.latitude, birth_input.longitude,
                                      b"W", swe.FLG_SIDEREAL)
            ascendant = float(angles[0])
            if not math.isfinite(ascendant) or not 0 <= ascendant < 360:
                raise VedicEphemerisUnavailable("Invalid ascendant")
        provenance = {"ephemeris": "Moshier analytical ephemeris", "library": "Swiss Ephemeris",
                      "version": swe.version, "source": SOURCE, "zodiac": "sidereal",
                      "ayanamsa": "Lahiri (SE_SIDM_LAHIRI)", "node": "mean lunar node",
                      "frame": "geocentric sidereal ecliptic of date",
                      "time_conversion": "IANA civil time → UTC → Swiss UT1",
                      "house_system": "Whole Sign" if ascendant is not None else None,
                      "scope": "natal; no current dasha or transit interpretation"}
    return rows, ascendant, provenance
