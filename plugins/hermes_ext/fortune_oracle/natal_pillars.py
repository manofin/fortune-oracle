"""Select confirmed natal pillars in the provider's canonical order."""
from collections.abc import Mapping

POSITIONS = ("year", "month", "day", "time")
_STEMS = "甲乙丙丁戊己庚辛壬癸"
_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
_VALID_PILLARS = frozenset(_STEMS[i % 10] + _BRANCHES[i % 12] for i in range(60))


def confirmed_pillars(eight_char):
    """Partition positions into valid pillars, missing positions, and invalid positions."""
    source = eight_char if isinstance(eight_char, Mapping) else {}
    pillars, missing, invalid = {}, [], []
    for position in POSITIONS:
        value = source.get(position)
        if value is None or value == "":
            missing.append(position)
        elif isinstance(value, str) and value in _VALID_PILLARS:
            pillars[position] = value
        else:
            invalid.append(position)
    return pillars, missing, invalid
