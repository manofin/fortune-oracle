"""Offline JPL DE440s / Skyfield ephemeris. No stub, downloads or geocoding.

Apparent geocentric tropical ecliptic of date; outer planets are system
barycenters (especially Pluto is not its body center). House intersections use
Skyfield's true equatorial/ecliptic frames and local apparent sidereal time.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from functools import lru_cache
import hashlib
import math
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

KERNEL_SHA256 = 'c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2'
KERNEL_URL = 'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp'
TARGETS = {'Sun':10,'Moon':301,'Mercury':1,'Venus':2,'Mars':4,
           'Jupiter':5,'Saturn':6,'Uranus':7,'Neptune':8,'Pluto':9}


class EphemerisUnavailable(Exception):
    pass


def kernel_path():
    return Path(os.environ.get('FORTUNE_EPHEMERIS_PATH') or Path(sys.prefix)/'ephemeris'/'de440s.bsp')


@lru_cache(maxsize=2)
def _load(path, size, mtime):
    try:
        from skyfield.api import load, load_file
        with Path(path).open('rb') as file:
            digest = hashlib.file_digest(file,'sha256').hexdigest()
        if digest != KERNEL_SHA256:
            raise EphemerisUnavailable('JPL kernel integrity check failed')
        kernel = load_file(path)
        return kernel,load.timescale(builtin=True)
    except ImportError:
        raise EphemerisUnavailable('Skyfield is not installed') from None
    except OSError:
        raise EphemerisUnavailable('JPL kernel could not be read') from None


def resources():
    try:
        path = kernel_path().resolve(strict=True)
        stat = path.stat()
        return _load(str(path),stat.st_size,stat.st_mtime_ns)
    except OSError:
        raise EphemerisUnavailable('JPL DE440s is not provisioned') from None


def backend_info():
    try:
        resources()
        return {'backend':'skyfield-jpl-de440s','status':'computed'}
    except EphemerisUnavailable:
        return {'backend':'skyfield-jpl-de440s','status':'unavailable'}


def birth_utc(birth_input):
    """Reject DST gaps/ambiguities rather than inventing an offset or a fold."""
    if birth_input.calendar_type != 'gregorian':
        raise ValueError('Only Gregorian dates are supported')
    if not birth_input.has_birth_time:
        raise ValueError('A birth time is required for ephemeris positions')
    values = birth_input.parse_birth_datetime()
    if values is None:
        raise ValueError('Invalid birth datetime')
    wall = datetime(**values)
    from .birth_clock import resolve_wall_time
    return resolve_wall_time(wall, birth_input.timezone)


def positions(utc):
    kernel,ts = resources()
    from skyfield.framelib import ecliptic_frame
    times = ts.from_datetimes([utc-timedelta(hours=1),utc,utc+timedelta(hours=1)])
    earth = kernel['earth'].at(times)
    result = []
    for name,target in TARGETS.items():
        _,longitude,_ = earth.observe(kernel[target]).apparent().frame_latlon(ecliptic_frame)
        values = longitude.degrees
        speed = ((float(values[2])-float(values[0])+180)%360-180)*12  # deg/day
        result.append({'name':name,'longitude':float(values[1])%360,
                       'speed':speed,'retrograde':speed < 0,'target':target})
    return result,ts.from_datetime(utc)


def horizon_angles(t,latitude,longitude):
    """Ascending ecliptic/horizon intersection and upper meridian intersection."""
    import numpy as np
    from skyfield.framelib import ecliptic_frame
    if not math.isfinite(latitude) or not math.isfinite(longitude) or abs(latitude) >= 89.99:
        raise ValueError('Horizon is undefined at the geographic poles')
    lst = math.radians((t.gast*15 + longitude)%360)
    lat = math.radians(latitude)
    up = np.array([math.cos(lat)*math.cos(lst),math.cos(lat)*math.sin(lst),math.sin(lat)])
    east = np.array([-math.sin(lst),math.cos(lst),0])
    frame = ecliptic_frame.rotation_at(t) @ t.M.T
    normal = frame[2]
    rising = np.cross(up,normal)
    if np.linalg.norm(rising) < 1e-12:
        raise ValueError('Degenerate horizon intersection')
    if np.dot(rising,east) < 0:
        rising = -rising
    meridian = np.cross(east,normal)
    if np.dot(meridian,[math.cos(lst),math.sin(lst),0]) < 0:
        meridian = -meridian
    def angle(vector):
        return math.degrees(math.atan2(float(np.dot(vector,frame[1])),float(np.dot(vector,frame[0]))))%360
    return angle(rising),angle(meridian)
