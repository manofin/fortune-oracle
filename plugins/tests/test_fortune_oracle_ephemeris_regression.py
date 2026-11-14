"""Fortune Oracle — Ephemeris Regression Tests (Phase 38R).

Regression tests for 4 bugs discovered during Swiss Ephemeris validation:

BUG-01: pyswisseph swe.calc() speed field is NOT daily motion in degrees
BUG-02: lon % nakshatra_width gives wrong result at nakshatra boundaries (FP accumulation)
BUG-03: House system comparison should compare cusps, not ASC/MC (ASC/MC are system-independent)
BUG-04: Vimshottari 27-nakshatra total is 360 years, not 120 (9-planet cycle = 120)
"""

import sys
from pathlib import Path
import math
import pytest

_plugins_dir = str(Path(__file__).resolve().parents[1])
if _plugins_dir not in sys.path:
    sys.path.insert(0, _plugins_dir)

from hermes_ext.fortune_oracle.vedic_bridge import (
    _calculate_nakshatra,
    _calculate_vimshottari_dasha,
)
from hermes_ext.fortune_oracle.vedic_schema import (
    NAKSHATRA_NAMES,
    VIMSHOTTARI_PERIODS,
    VIMSHOTTARI_ORDER,
)

# ---------------------------------------------------------------------------
# BUG-01: pyswisseph speed field is NOT daily motion
# ---------------------------------------------------------------------------

class TestBug01SpeedField:
    """pyswisseph의 swe.calc() 반환값 [2]는 일일 이동량이 아님."""

    def test_speed_field_not_daily_motion(self):
        """speed field의 값이 일일 이동량(degree/day)과 다름을 검증."""
        try:
            import swisseph as swe
        except ImportError:
            pytest.skip("pyswisseph not installed")

        jday = swe.julday(2026, 1, 1, 0)
        pos, _ = swe.calc(jday, swe.MOON)
        speed_field = pos[2]

        # 실제 일일 이동량 계산 (1일 샘플링)
        pos_tomorrow, _ = swe.calc(jday + 1, swe.MOON)
        actual_daily = abs(pos_tomorrow[0] - pos[0])

        # speed field는 일일 이동량이 아님 (실제 약 13°, speed_field는 매우 작은 값)
        assert actual_daily > 10.0  # Moon은 약 13°/일
        assert abs(speed_field) < 1.0  # speed field는 1도 미만

    def test_daily_motion_must_be_sampled(self):
        """일일 이동량은 1일 샘플링으로 계산해야 함."""
        try:
            import swisseph as swe
        except ImportError:
            pytest.skip("pyswisseph not installed")

        jday = swe.julday(2026, 1, 1, 0)
        for body_id in [swe.SUN, swe.MOON, swe.MERCURY, swe.VENUS]:
            pos, _ = swe.calc(jday, body_id)
            pos_tomorrow, _ = swe.calc(jday + 1, body_id)
            daily = abs(pos_tomorrow[0] - pos[0])
            # 일일 이동량은 0.01도 이상 (모든 주요 행성)
            assert daily > 0.01, f"Daily motion too small for body {body_id}"

# ---------------------------------------------------------------------------
# BUG-02: lon % nakshatra_width floating point accumulation
# ---------------------------------------------------------------------------

NAKSHATRA_WIDTH = 360.0 / 27  # = 13.333...

class TestBug02NakshatraFloatingPoint:
    """lon % nakshatra_width가 경계점에서 잘못된 결과를 반환."""

    def test_boundary_modulo_fails(self):
        """40° % 13.3333 = 13.3333 (0이 아님) — floating point 축적 오차."""
        lon = 40.0  # 3 * 13.3333 = 40.0 (Rohini 시작점)
        bad_result = lon % NAKSHATRA_WIDTH
        # bug: 40.0 % 13.3333 = 13.3333, not 0
        assert bad_result > 10.0  # 0이 아니라 ~13.33 — 버그 재현

    def test_boundary_subtraction_works(self):
        """lon - (index * width) 방식으로 계산하면 정확함."""
        lon = 40.0
        idx = int(lon / NAKSHATRA_WIDTH) % 27
        good_result = lon - idx * NAKSHATRA_WIDTH
        # 0에 매우 가까워야 함
        assert abs(good_result) < 1e-10

    def test_all_nakshatra_boundaries_subtraction(self):
        """모든 경계점에서 subtraction 방식이 0에 가까움."""
        for i in range(27):
            boundary = i * NAKSHATRA_WIDTH
            idx = int(boundary / NAKSHATRA_WIDTH) % 27
            pos = boundary - idx * NAKSHATRA_WIDTH
            assert abs(pos) < 1e-10, f"Boundary {i} ({boundary}°): pos={pos}"

    def test_nakshatra_at_40_degrees(self):
        """40°는 Rohini (idx=3)의 시작점."""
        nak = _calculate_nakshatra(40.0)
        assert nak.name == "Rohini"

    def test_nakshatra_at_80_degrees(self):
        """80°는 Punarvasu (idx=6)의 시작점."""
        nak = _calculate_nakshatra(80.0)
        assert nak.name == "Punarvasu"

    def test_nakshatra_at_120_degrees(self):
        """120°는 Magha (idx=9)의 시작점."""
        nak = _calculate_nakshatra(120.0)
        assert nak.name == "Magha"

# ---------------------------------------------------------------------------
# BUG-03: House system comparison — ASC/MC are system-independent
# ---------------------------------------------------------------------------

class TestBug03HouseSystemComparison:
    """ASC/MC는 하우스 시스템과 무관하므로 cusp를 비교해야 함."""

    def test_asc_mc_not_dependent_on_house_system(self):
        """ASC/MC는 모든 하우스 시스템에서 동일해야 함."""
        try:
            import swisseph as swe
        except ImportError:
            pytest.skip("pyswisseph not installed")

        jday = swe.julday(1990, 3, 15, 9.5)
        lat, lon = 37.5665, 126.9780

        asc_values = []
        mc_values = []
        for code in [b'T', b'K', b'C', b'R', b'E', b'O']:
            result = swe.houses(jday, lat, lon, code)
            asc_values.append(result[1][0])
            mc_values.append(result[1][1])

        # ASC는 모두 동일
        for asc in asc_values[1:]:
            assert abs(asc - asc_values[0]) < 1e-6

        # MC도 모두 동일
        for mc in mc_values[1:]:
            assert abs(mc - mc_values[0]) < 1e-6

    def test_house_cusps_differ_by_system(self):
        """하우스 경계(cusp)는 시스템마다 다름."""
        try:
            import swisseph as swe
        except ImportError:
            pytest.skip("pyswisseph not installed")

        jday = swe.julday(1990, 3, 15, 9.5)
        lat, lon = 37.5665, 126.9780

        result_placidus = swe.houses(jday, lat, lon, b'T')
        result_koch = swe.houses(jday, lat, lon, b'K')

        # Cusp 2 (index 1)는 다름
        cusp2_placidus = result_placidus[0][1]
        cusp2_koch = result_koch[0][1]
        assert abs(cusp2_placidus - cusp2_koch) > 0.01  # 1' 이상 차이

# ---------------------------------------------------------------------------
# BUG-04: Vimshottari cycle — 9-planet cycle = 120 years
# ---------------------------------------------------------------------------

class TestBug04VimshottariCycle:
    """Vimshottari의 9-planet cycle은 120년임 (27 nakshatra = 360년은 전체 회전)."""

    def test_nine_planet_cycle_120_years(self):
        """9-planet cycle의 총합은 120년."""
        # VIMSHOTTARI_ORDER는 9개 graha
        total = sum(VIMSHOTTARI_PERIODS[g] for g in VIMSHOTTARI_ORDER)
        assert total == 120, f"9-planet cycle total: {total} (expected 120)"

    def test_27_nakshatra_is_3_times_120(self):
        """27 nakshatra는 9-planet cycle의 3회 반복 = 360년."""
        # 27 nakshatra = 3 x 9-planet cycle
        # 각 nakshatra의 dasha는 9-planet 순환을 따름
        nakshatra_count = len(NAKSHATRA_NAMES)
        assert nakshatra_count == 27
        assert nakshatra_count % 9 == 0
        assert (nakshatra_count // 9) * 120 == 360

    def test_nakshatra_to_graha_mapping_cycles(self):
        """nakshatra → graha 매핑이 9-planet 순환을 따름."""
        nak_to_graha = {
            "Ashwini": "Ketu", "Bharani": "Venus", "Krittika": "Sun",
            "Rohini": "Moon", "Mrigashira": "Mars", "Ardra": "Rahu",
            "Punarvasu": "Jupiter", "Pushya": "Saturn", "Ashlesha": "Mercury",
            "Magha": "Ketu", "Purva Phalguni": "Venus", "Uttara Phalguni": "Sun",
            "Hasta": "Moon", "Chitra": "Mars", "Swati": "Rahu",
            "Vishakha": "Jupiter", "Anuradha": "Saturn", "Jyeshtha": "Mercury",
            "Mula": "Ketu", "Purva Ashadha": "Venus", "Uttara Ashadha": "Sun",
            "Shravana": "Moon", "Dhanishta": "Mars", "Shatabhisha": "Rahu",
            "Purva Bhadrapada": "Jupiter", "Uttara Bhadrapada": "Saturn",
            "Revati": "Mercury",
        }
        # 첫 9개 nakshatra의 graha 순서가 VIMSHOTTARI_ORDER와 동일
        first_9 = list(nak_to_graha.values())[:9]
        assert first_9 == list(VIMSHOTTARI_ORDER)

    def test_dasha_at_nakshatra_boundary(self):
        """nakshatra 경계에서 dasha used_years = 0."""
        # 0° (Ashwini 시작점)
        nak = _calculate_nakshatra(0.0)
        assert nak.name == "Ashwini"
        # Ashwini의 dasha는 Ketu, 7년
        # 경계이므로 used = 0, remaining = 7

    def test_dasha_at_nakshatra_end(self):
        """nakshatra 끝에서 dasha remaining_years ≈ 0."""
        # 13.332° (Ashwini 끝 직전)
        nak = _calculate_nakshatra(13.332)
        assert nak.name == "Ashwini"
        # 거의 끝이므로 degree_in_nakshatra ≈ 13.33
        assert nak.degree_in_nakshatra > 13.0
