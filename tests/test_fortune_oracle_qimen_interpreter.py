#!/usr/bin/env python3
"""Fortune Oracle — Qimen Interpreter tests (Phase 35 + Gate 4.2).

Tests qimen_interpreter sanitize guard, formatter, and alias behavior.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle.qimen_schema import (
    QIMEN_DISCLAIMER,
    QimenChart,
    QimenPalace,
    QimenQuery,
    QimenResult,
)
from hermes_ext.fortune_oracle.qimen_interpreter import (
    _sanitize,
    DOOR_KR,
    GOD_KR,
    STAR_KR,
    format_qimen_empty,
    format_qimen_result,
    _detect_fuyin_fanyin,
    _detect_basic_geju,
)
from hermes_ext.fortune_oracle.platforms import telegram


# --- Sanitize guard tests ---

def test_sanitize_removes_dataclass_repr():
    text = "QimenChart(ok=True)"
    result = _sanitize(text)
    assert "QimenChart" not in result
    assert "[SANITIZED]" in result


def test_sanitize_removes_traceback():
    text = "Traceback (most recent call last)"
    result = _sanitize(text)
    assert "traceback" not in result.lower()


def test_sanitize_removes_default_factory():
    text = "default_factory=list"
    result = _sanitize(text)
    assert "default_factory" not in result


def test_sanitize_removes_file_line():
    text = 'File "/home/test.py", line 42'
    result = _sanitize(text)
    assert "[SANITIZED]" in result


def test_sanitize_preserves_normal_text():
    text = "기문둔갑 판입니다. 절기: 소만"
    result = _sanitize(text)
    assert result == text


# --- Formatter tests ---

def test_format_error_result():
    result = QimenResult.error("TEST", "test error")
    text = format_qimen_result(result)
    assert "기문둔갑" in text
    assert QIMEN_DISCLAIMER in text
    assert "QimenResult(" not in text
    assert "dataclass" not in text


def test_format_no_chart():
    result = QimenResult(ok=True, chart=None)
    text = format_qimen_result(result)
    assert "QimenChart(" not in text
    assert "dataclass" not in text


def test_format_with_chart():
    chart = QimenChart(
        method="拆補",
        ganzhi="丙午年癸巳月壬寅日丙午時",
        jie_qi="小滿",
        pai_ju="陽遁二局中元",
        xun_shou="辛",
        xun_kong="日空:辰巳 時空:寅卯",
        ju_day="丁壬日",
        zhi_fu_stem="壬",
        zhi_fu_star="心",
        zhi_shi_door="開",
        tian_yi="英",
        horse_star={"天馬": "午", "驛馬": "申"},
        palaces={
            "坎": QimenPalace(
                palace_name="坎",
                sky_stem="庚",
                earth_stem="乙",
                door="驚",
                star="輔",
                god="勾",
                life_phase="長生",
            ),
            "離": QimenPalace(
                palace_name="離",
                sky_stem="壬",
                earth_stem="丙",
                door="傷",
                star="心",
                god="符",
            ),
        },
    )
    result = QimenResult(ok=True, chart=chart, query=QimenQuery(2026, 5, 28, 12, 30, question="이사"))
    text = format_qimen_result(result)

    # Core content checks
    assert "기문둔갑" in text
    assert "拆補" in text
    assert "2026년 5월 28일 12시 30분" in text
    assert "Asia/Seoul" in text
    assert "이사" not in text  # Do not copy the private question into a public reading.
    assert "丙午年癸巳月壬寅日丙午時" in text
    assert "小滿" in text
    assert "陽遁二局中元" in text
    assert QIMEN_DISCLAIMER in text

    # Sanitize guard checks
    assert "QimenChart(" not in text
    assert "QimenResult(" not in text
    assert "QimenPalace(" not in text
    assert "QimenQuery(" not in text
    assert "dataclass" not in text
    assert "default_factory" not in text
    assert "traceback" not in text.lower()


def test_format_empty():
    text = format_qimen_empty()
    assert "기문둔갑" in text
    assert "QimenChart(" not in text


# --- Alias tests ---

def test_telegram_qimen_alias():
    parsed = telegram.parse_command("/qimen")
    assert parsed is not None
    assert parsed["command"] == "qimen"


def test_telegram_korean_qimen_alias():
    parsed = telegram.parse_command("/기문")
    assert parsed is not None
    assert parsed["command"] == "qimen"


def test_telegram_qimen_with_args():
    parsed = telegram.parse_command("/qimen 2026-05-28 21:30 이사 방향")
    assert parsed is not None
    assert parsed["command"] == "qimen"
    assert "2026-05-28" in parsed["args"]
    assert "이사 방향" in parsed["args"]


def test_telegram_korean_qimen_with_args():
    parsed = telegram.parse_command("/기문 지금 이 선택을 점검해줘")
    assert parsed is not None
    assert parsed["command"] == "qimen"
    assert "지금 이 선택을 점검해줘" in parsed["args"]


def test_telegram_qimen_in_canonical_commands():
    assert "qimen" in telegram.bot_command_names()


# --- Mapping collision tests (Fix 3) ---

def test_door_kr_no_value_collision():
    """8문 매핑에서 한글 값이 중복되지 않아야 한다."""
    values = list(DOOR_KR.values())
    assert len(values) == len(set(values)), f"DOOR_KR collision: {values}"


def test_star_kr_no_value_collision():
    """9성 매핑에서 한글 값이 중복되지 않아야 한다."""
    values = list(STAR_KR.values())
    assert len(values) == len(set(values)), f"STAR_KR collision: {values}"


def test_god_kr_no_value_collision():
    """8신 매핑에서 한글 값이 중복되지 않아야 한다."""
    values = list(GOD_KR.values())
    assert len(values) == len(set(values)), f"GOD_KR collision: {values}"


def test_door_kr_has_all_eight_doors():
    """8문은 8개 항목이어야 한다."""
    assert len(DOOR_KR) == 8, f"Expected 8 doors, got {len(DOOR_KR)}"


def test_star_kr_has_all_nine_stars():
    """9성은 9개 항목이어야 한다."""
    assert len(STAR_KR) == 9, f"Expected 9 stars, got {len(STAR_KR)}"


def test_god_kr_has_all_ten_gods():
    """직부·등사·태음·육합·구진·백작·백호·현무·구천·구지."""
    assert len(GOD_KR) == 10, f"Expected 10 gods, got {len(GOD_KR)}"


# ------------------------------------------------------------------
# Gate 4.2 신규 테스트 (geju detector)
# ------------------------------------------------------------------

from hermes_ext.fortune_oracle.qimen_schema import QimenGeju


def test_detect_fuyin_excludes_center():
    """伏吟 판정 시 중궁 명시적 제외 확인."""
    chart = QimenChart(
        palaces={
            "坎": QimenPalace(palace_name="坎", sky_stem="甲", earth_stem="甲"),
            "坤": QimenPalace(palace_name="坤", sky_stem="乙", earth_stem="乙"),
            "艮": QimenPalace(palace_name="艮", sky_stem="丙", earth_stem="丙"),
            # 中은 제외되어야 함
            "中": QimenPalace(palace_name="中", sky_stem="丁", earth_stem="丁"),
        }
    )
    fuyin, fanyin = _detect_fuyin_fanyin(chart)
    assert fuyin is True   # 3개 외곽 중복
    assert fanyin is False


def test_detect_basic_geju_pattern_only():
    """격국 출력이 패턴 서술형만 생성되는지 확인."""
    chart = QimenChart(
        zhi_fu_star="心",
        palaces={
            "中": QimenPalace(palace_name="中", door="生"),
            "坎": QimenPalace(palace_name="坎", door="死"),
        }
    )
    geju = _detect_basic_geju(chart)
    assert isinstance(geju, QimenGeju)
    assert geju.fuyin is False
    # 중궁은 명시적 제외 → 생문이 있어도 길격 리스트에 없어야 함
    assert not any("중" in s for s in geju.detected_ji_ge)
    # 사문은 흉격으로 유지
    assert any("死문이" in s for s in geju.detected_xiong_ge)
    # 단정 표현 없음
    assert "길하다" not in str(geju)
    assert "흉하다" not in str(geju)


def test_geju_summary_is_descriptive():
    """summary가 단정적이지 않고 서술형인지."""
    chart = QimenChart(
        palaces={"坎": QimenPalace(palace_name="坎", door="生")}
    )
    geju = _detect_basic_geju(chart)
    if geju.summary:
        assert "패턴" in geju.summary or "감지" in geju.summary or "위치" in geju.summary


# Gate 4.2 확장: 신규 격국 패턴 테스트
def test_detect_kaimen_ji_ge():
    """開門이 길격으로 감지되는지."""
    chart = QimenChart(
        palaces={"離": QimenPalace(palace_name="離", door="開")}
    )
    geju = _detect_basic_geju(chart)
    assert any("開門이" in s for s in geju.detected_ji_ge)


def test_detect_shangmen_xiong_ge():
    """傷門이 흉격으로 감지되는지."""
    chart = QimenChart(
        palaces={"艮": QimenPalace(palace_name="艮", door="傷")}
    )
    geju = _detect_basic_geju(chart)
    assert any("傷門이" in s for s in geju.detected_xiong_ge)


def test_center_palace_excluded_from_geju():
    """중궁(中)은 격국 패턴에서 명시적으로 제외되어야 한다."""
    chart = QimenChart(
        palaces={
            "中": QimenPalace(palace_name="中", door="生"),
            "巽": QimenPalace(palace_name="巽", door="死"),
        }
    )
    geju = _detect_basic_geju(chart)
    # 중궁에서 생문 배치가 있어도 길격 리스트에 없어야 함
    assert not any("중" in s for s in geju.detected_ji_ge)
    # 외곽 사문은 정상적으로 흉격에 포함됨
    assert any("死문이" in s for s in geju.detected_xiong_ge)


def test_geju_no_assertive_phrases():
    """격국 출력에 '길하다/흉하다' 등 단정 표현이 없어야 한다."""
    chart = QimenChart(
        palaces={
            "巽": QimenPalace(palace_name="巽", door="生"),
            "坎": QimenPalace(palace_name="坎", door="死"),
            "坤": QimenPalace(palace_name="坤", door="傷"),
        }
    )
    geju = _detect_basic_geju(chart)
    combined = " ".join(geju.detected_ji_ge + geju.detected_xiong_ge + [geju.summary])
    assert "길하다" not in combined
    assert "흉하다" not in combined
    assert "좋다" not in combined
    assert "나쁘다" not in combined
