# Fortune Oracle - Bazi Boundary Interpreter
# Phase 20: 경계 조건 해석 및 사용자 안내 텍스트

from .bazi_boundary import (
    IPCHUN_BOUNDARY_NOTE,
    SOLAR_TERM_DAY_NOTE,
    JASI_BOUNDARY_NOTE,
    TRUE_SOLAR_TIME_NOTE,
    SUPPORTED_DATE_RANGE,
)


def format_boundary_limitations() -> str:
    """
    사용자에게 표시할 경계 조건 한계점 안내 텍스트를 반환합니다.
    공포 조장 없이 사실 기반으로 안내합니다.
    """
    lines = [
        '[ 사주 계산 정밀도 안내 ]',
        '',
        '1. 연주(年柱) 경계',
        f'   {IPCHUN_BOUNDARY_NOTE}',
        '',
        '2. 월주(月柱) 경계',
        f'   {SOLAR_TERM_DAY_NOTE}',
        '',
        '3. 시주(時柱) 경계',
        f'   {JASI_BOUNDARY_NOTE}',
        '',
        '4. 진태양시(眞太陽時)',
        f'   {TRUE_SOLAR_TIME_NOTE}',
        '',
        f'5. 지원 날짜 범위: {SUPPORTED_DATE_RANGE[0]}년 ~ {SUPPORTED_DATE_RANGE[1]}년',
        '',
        '※ 위 한계에 해당하는 시각에 태어나신 경우 월주/연주가 다르게 산출될 수 있습니다.',
        '  이는 사주 계산 방식의 일반적인 특성이며 결과는 참고용입니다.',
    ]
    return '\n'.join(lines)


def get_precision_note(exact_flag: bool) -> str:
    """
    exact_flag에 따른 절기 계산 정밀도 안내 메시지를 반환합니다.
    """
    if exact_flag:
        return '절기 정밀 계산 적용'
    return '절기 검증된 허용오차 내 계산 (기본값)'
