"""Resolve a civil birth time without guessing across DST gaps or folds."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def civil_day_utc_bounds(day, zone_name):
    """Earliest/latest possible instant on a local date, including midnight DST.

    A skipped date has no interval. Folds retain both candidates; a midnight
    gap does not turn an otherwise valid date into an invented midnight.
    """
    zone = ZoneInfo(zone_name)
    def candidates(minute, second):
        wall = datetime(day.year, day.month, day.day, minute // 60, minute % 60, second)
        values = []
        for fold in (0, 1):
            utc = wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == wall:
                values.append(utc)
        return values
    first = next((values for minute in range(1440) if (values := candidates(minute, 0))), None)
    last = next((values for minute in range(1439, -1, -1) if (values := candidates(minute, 59))), None)
    if first is None or last is None:
        raise ValueError('This local date does not exist in the selected time zone')
    return min(first), max(last)


def resolve_wall_time(wall: datetime, zone_name: str):
    if wall.tzinfo is not None:
        raise ValueError('Expected a naive civil datetime')
    zone = ZoneInfo(zone_name)
    candidates = set()
    for fold in (0, 1):
        utc = wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == wall:
            candidates.add(utc)
    if len(candidates) != 1:
        raise ValueError('Birth time is ambiguous or nonexistent in this time zone')
    return candidates.pop()
