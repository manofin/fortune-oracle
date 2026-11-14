"""Describe I Ching line graphics in words without changing any drawn values."""
import re
from .localization import language_code

LINE_NAMES = {
    'ko': {6:'노음, 변화하는 음효', 7:'소양, 변하지 않는 양효',
           8:'소음, 변하지 않는 음효', 9:'노양, 변화하는 양효'},
    'en': {6:'old yin, changing', 7:'young yang, unchanging',
           8:'young yin, unchanging', 9:'old yang, changing'},
}


def iching_speech_text(reading, language='ko'):
    code = language_code(language)
    values = reading['lines']
    if len(values) != 6 or any(type(value) is not int or value not in LINE_NAMES[code] for value in values):
        raise ValueError('Six valid I Ching line values are required')
    spoken = []
    for row in reading['text'].splitlines():
        match = re.match(r'^(\d)효\s' if code == 'ko' else r'^Line (\d):', row)
        if match and 1 <= int(match.group(1)) <= 6:
            index = int(match.group(1))
            name = LINE_NAMES[code][values[index-1]]
            row = f'{index}효: {name}.' if code == 'ko' else f'Line {index}: {name}.'
        spoken.append(row)
    return '\n'.join(spoken)
