# Fortune Oracle - Bazi Boundary Conditions & Accuracy Suite
# Phase 20: 사주 경계 조건 정의 및 검증

IPCHUN_BOUNDARY_NOTE = '입춘 전후 연주 경계는 절기 exact flag에 의존합니다.'
SOLAR_TERM_DAY_NOTE = '절기 당일 월주 경계는 검증된 허용오차 내 계산입니다.'
JASI_BOUNDARY_NOTE = '子시(23:00-01:00) 처리: 야자시(夜子時, 23:00-) 지원은 PENDING입니다.'
TRUE_SOLAR_TIME_NOTE = 'longitude 기반 진태양시는 현재 미지원입니다.'

SUPPORTED_DATE_RANGE = (1800, 2100)
DEFAULT_TIMEZONE = 'Asia/Seoul'

# 시지(時支) 매핑 테이블: (start_hour, end_hour_exclusive) -> branch
_HOUR_BRANCH_MAP = [
    (0, 1, '子'),
    (1, 3, '丑'),
    (3, 5, '寅'),
    (5, 7, '卯'),
    (7, 9, '辰'),
    (9, 11, '巳'),
    (11, 13, '午'),
    (13, 15, '未'),
    (15, 17, '申'),
    (17, 19, '酉'),
    (19, 21, '戌'),
    (21, 23, '亥'),
    (23, 24, '子'),
]


def validate_birth_datetime(year: int, month: int, day: int,
                             hour: int, minute: int) -> tuple:
    """
    생년월일시분 유효성 검사.
    Returns (bool, str) — (is_valid, message)
    """
    if not (SUPPORTED_DATE_RANGE[0] <= year <= SUPPORTED_DATE_RANGE[1]):
        return (False,
                f'연도 범위 오류: {year}. 지원 범위는 {SUPPORTED_DATE_RANGE[0]}-{SUPPORTED_DATE_RANGE[1]}입니다.')
    if not (1 <= month <= 12):
        return (False, f'월 오류: {month}. 1-12 사이여야 합니다.')
    if not (1 <= day <= 31):
        return (False, f'일 오류: {day}. 1-31 사이여야 합니다.')
    if not (0 <= hour <= 23):
        return (False, f'시 오류: {hour}. 0-23 사이여야 합니다.')
    if not (0 <= minute <= 59):
        return (False, f'분 오류: {minute}. 0-59 사이여야 합니다.')
    return (True, '유효한 생년월일시분입니다.')


def classify_hour_branch(hour: int, minute: int = 0) -> dict:
    """
    시각(hour, minute)에 해당하는 시지(時支)를 반환합니다.
    Returns {'branch': str, 'note': str, 'warning': str|None}
    """
    warning = None

    if hour == 23:
        branch = '子'
        warning = '야자시 경계: 다음날 子시로 처리하는 관례도 있습니다.'
    else:
        branch = '子'  # default fallback
        for start, end, br in _HOUR_BRANCH_MAP:
            if start <= hour < end:
                branch = br
                break

    return {
        'branch': branch,
        'note': JASI_BOUNDARY_NOTE if hour == 23 else '',
        'warning': warning,
    }


def get_month_exact_flag_status() -> str:
    """월주 exact flag 지원 상태를 반환합니다."""
    return 'getMonthInGanZhiExact: available via lunar-javascript (local only)'


# 테스트용 fixture 케이스
BOUNDARY_FIXTURES: list = [
    {
        'id': 'ipchun_before',
        'label': '입춘 전 (연주 경계 이전)',
        'year': 2024,
        'month': 2,
        'day': 3,
        'note': IPCHUN_BOUNDARY_NOTE,
    },
    {
        'id': 'ipchun_after',
        'label': '입춘 후 (연주 경계 이후)',
        'year': 2024,
        'month': 2,
        'day': 5,
        'note': IPCHUN_BOUNDARY_NOTE,
    },
    {
        'id': 'solar_term_day',
        'label': '절기 당일 월주 경계',
        'note': SOLAR_TERM_DAY_NOTE,
    },
    {
        'id': 'jasi_boundary',
        'label': '야자시 경계 (23:00)',
        'hour': 23,
        'note': JASI_BOUNDARY_NOTE,
    },
]
