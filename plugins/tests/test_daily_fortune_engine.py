#!/usr/bin/env python3
"""Slice 1 회귀 테스트 — 개인화 일일 운세 엔진.

검증 축:
  1. 일진 정확성 (lunar-javascript 권위소스와 대조)
  2. 개인화 (프로필·날짜에 따라 결과가 실제로 달라지는가)
  3. 결정론 (동일 입력 → 동일 출력)
  4. 영역(aspect) 5종 구분
  5. 프라이버시 (출생정보 원문 비노출)
  6. fail-closed (프로필 없음 → None, 예외 전파 없음)
"""

from __future__ import annotations

import datetime
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes_ext.fortune_oracle.daily_fortune_engine import (
    _day_pillar_for,
    build_personalized_daily,
    render_personalized_daily_text,
)

NODE_LUNAR = str(
    Path(__file__).resolve().parents[1] / "hermes_ext" / "fortune_oracle"
    / "scripts" / "node_modules" / "lunar-javascript"
)

PROFILES = {
    "A": {"birth_date": "1990-05-15", "birth_time": "07:30", "birth_place": "서울", "gender": "male"},
    "B": {"birth_date": "1988-03-02", "birth_time": "22:10", "birth_place": "부산", "gender": "female"},
    "C": {"birth_date": "2001-01-20", "birth_time": "11:11", "birth_place": "대구", "gender": "female"},
    "NO_GENDER": {"birth_date": "1975-11-11", "birth_time": "03:03", "birth_place": "대전", "gender": ""},
}

H2K = {
    "甲": "갑", "乙": "을", "丙": "병", "丁": "정", "戊": "무",
    "己": "기", "庚": "경", "辛": "신", "壬": "임", "癸": "계",
    "子": "자", "丑": "축", "寅": "인", "卯": "묘", "辰": "진", "巳": "사",
    "午": "오", "未": "미", "申": "신", "酉": "유", "戌": "술", "亥": "해",
}

T = datetime.date(2026, 10, 3)


class TestDayPillar(unittest.TestCase):
    """일진이 lunar-javascript와 정확히 일치해야 한다."""

    DATES = [
        (2000, 1, 1), (2000, 1, 2), (1990, 5, 15), (2026, 10, 3), (2026, 10, 4),
        (2024, 2, 10), (1970, 1, 1), (2033, 12, 22), (1999, 12, 31), (2026, 1, 1),
        (2000, 2, 29), (1980, 8, 8), (2026, 12, 31), (2010, 11, 11), (2001, 2, 28),
        (2026, 6, 15), (1995, 3, 3),
    ]

    def test_matches_lunar_javascript(self):
        js = (
            "const {Solar}=require('%s');const out=[];"
            "for(const[y,m,d]of %s) out.push("
            "Solar.fromYmdHms(y,m,d,0,0,0).getLunar().getDayInGanZhiExact());"
            "console.log(JSON.stringify(out));" % (NODE_LUNAR, json.dumps(self.DATES))
        )
        proc = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, f"node 실패: {proc.stderr[:300]}")
        auth = json.loads(proc.stdout)
        self.assertEqual(len(auth), len(self.DATES))
        for (y, m, d), expected_hanzi in zip(self.DATES, auth):
            got = _day_pillar_for(datetime.date(y, m, d))
            want = H2K[expected_hanzi[0]] + H2K[expected_hanzi[1]]
            self.assertEqual(got, want, f"{y}-{m:02d}-{d:02d}: got {got}, want {want}")

    def test_consecutive_days_advance_by_one(self):
        base = _day_pillar_for(T)
        nxt = _day_pillar_for(T + datetime.timedelta(days=1))
        stems = list("갑을병정무기경신임계")
        branches = list("자축인묘진사오미신유술해")
        si = stems.index(base[0])
        bi = branches.index(base[1])
        self.assertEqual(stems[(si + 1) % 10], nxt[0])
        self.assertEqual(branches[(bi + 1) % 12], nxt[1])


class TestPersonalization(unittest.TestCase):
    def test_different_profiles_differ(self):
        scores = {
            k: build_personalized_daily(p, target_date=T)["score"]
            for k, p in PROFILES.items()
        }
        self.assertGreaterEqual(len(set(scores.values())), 3, f"프로필 간 분산 부족: {scores}")

    def test_day_master_and_relation_resolved(self):
        """한자 일간이어도 오행/관계가 판정되어야 한다 (빈칸 회귀 방지)."""
        for key, prof in PROFILES.items():
            d = build_personalized_daily(prof, target_date=T)
            self.assertIsNotNone(d, key)
            self.assertTrue(d["day_master"], key)
            self.assertIn(d["relation"], {"same", "output", "input", "pressure", "wealth"}, key)
            self.assertTrue(d["favorable_elements"], key)

    def test_aspects_are_distinguished(self):
        for key, prof in PROFILES.items():
            vals = {
                a: build_personalized_daily(prof, target_date=T, aspect=a)["score"]
                for a in ("종합", "활동", "관계", "재물", "건강")
            }
            self.assertGreaterEqual(
                len(set(vals.values())), 3, f"{key} 영역 구분 부족: {vals}"
            )

    def test_date_changes_output(self):
        series = [
            build_personalized_daily(PROFILES["A"], target_date=T + datetime.timedelta(days=i))
            for i in range(30)
        ]
        pillars = {d["day_pillar"] for d in series}
        self.assertGreaterEqual(len(pillars), 25, "30일간 일진이 거의 변하지 않음")


class TestDeterminism(unittest.TestCase):
    def test_same_input_same_output(self):
        a = build_personalized_daily(PROFILES["A"], target_date=T)
        b = build_personalized_daily(PROFILES["A"], target_date=T)
        self.assertEqual(a, b)

    def test_score_within_bounds(self):
        for prof in PROFILES.values():
            for asp in ("종합", "활동", "관계", "재물", "건강"):
                score = build_personalized_daily(prof, target_date=T, aspect=asp)["score"]
                self.assertGreaterEqual(score, 0.0)
                self.assertLessEqual(score, 100.0)


class TestPrivacy(unittest.TestCase):
    def test_no_birth_data_in_output(self):
        secrets = [
            "1990-05-15", "07:30", "서울", "1988-03-02", "22:10",
            "부산", "2001-01-20", "11:11", "대구", "1975", "11-11",
        ]
        text = "".join(
            (render_personalized_daily_text(p, target_date=T) or "") for p in PROFILES.values()
        )
        found = [s for s in secrets if s in text]
        self.assertEqual(found, [], f"출생정보 원문 노출: {found}")

    def test_disclaimer_present(self):
        for prof in PROFILES.values():
            d = build_personalized_daily(prof, target_date=T)
            self.assertIn("오락과 자기성찰용", d["disclaimer"])


class TestFailClosed(unittest.TestCase):
    def test_missing_profile_returns_none(self):
        for bad in ({}, None, {"birth_time": "07:00"}, {"birth_date": ""}):
            self.assertIsNone(build_personalized_daily(bad, target_date=T))

    def test_render_returns_none_not_exception(self):
        self.assertIsNone(render_personalized_daily_text({}, target_date=T))
        self.assertIsNone(render_personalized_daily_text(None, target_date=T))

    def test_malformed_birth_date_does_not_raise(self):
        for bad_date in ("not-a-date", "1990", "1990-13-45", "0000-00-00"):
            prof = {"birth_date": bad_date, "birth_time": "07:30", "gender": "male"}
            try:
                result = build_personalized_daily(prof, target_date=T)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"{bad_date}에서 예외 전파: {type(exc).__name__}: {exc}")
            self.assertTrue(result is None or result.get("ok") is True)


class TestIntegrationAndCorrections(unittest.TestCase):
    def test_element_tables_match_existing_engine(self):
        from hermes_ext.fortune_oracle import daily_fortune_engine as engine, yongshen
        for stem, element in yongshen._STEM_ELEMENT.items():
            self.assertEqual(engine._stem_element(stem), element)
            self.assertEqual(engine._stem_element(engine._to_korean_stem(stem)), element)
        for branch, element in yongshen._BRANCH_ELEMENT.items():
            self.assertEqual(engine._branch_element(branch), element)
            self.assertEqual(engine._branch_element(engine._to_korean_branch(branch)), element)

    def test_controlling_and_controlled_relations(self):
        from hermes_ext.fortune_oracle.daily_fortune_engine import _element_day_relation
        self.assertEqual(_element_day_relation("목", "토"), "wealth")
        self.assertEqual(_element_day_relation("목", "금"), "pressure")

    def test_aspect_summary_matches_requested_scores(self):
        summary = build_personalized_daily(PROFILES["A"], target_date=T)
        for aspect, score in summary["aspect_scores"].items():
            result = build_personalized_daily(PROFILES["A"], target_date=T, aspect=aspect)
            self.assertEqual(score, result["score"])

    def test_invalid_birth_date_types_fall_back(self):
        for value in (19900515, [], {}):
            self.assertIsNone(build_personalized_daily({"birth_date": value}, target_date=T))

    def test_daily_route_uses_real_engine_and_plain_text(self):
        from hermes_ext.fortune_oracle import core
        with patch("hermes_ext.fortune_oracle.daily_fortune_engine._kst_today", return_value=T):
            text = core.render_daily_fortune(profile=PROFILES["A"])
        self.assertEqual(text, render_personalized_daily_text(PROFILES["A"], target_date=T))
        reading = build_personalized_daily(PROFILES["A"], target_date=T)
        self.assertEqual(text.splitlines(), reading["lines"] + [reading["disclaimer"]])
        headings = ("이날의 해석:", "해볼 일:", "주의할 점:", "해석 근거:", "해석의 한계:")
        lines = text.splitlines()
        positions = [next(i for i, line in enumerate(lines) if line.startswith(heading))
                     for heading in headings]
        self.assertEqual(positions, sorted(set(positions)))
        for markup in ("**", "#", "`"):
            self.assertNotIn(markup, text)

    def test_non_daily_routes_do_not_call_engine(self):
        from hermes_ext.fortune_oracle import core
        with patch("hermes_ext.fortune_oracle.daily_fortune_engine.render_personalized_daily_text") as render:
            for day, label in (("tomorrow", "내일"), ("week", "이번 주")):
                self.assertIn(label, core.render_fortune(day, profile=PROFILES["A"]))
            render.assert_not_called()

    def test_engine_exception_or_empty_result_uses_fallback(self):
        from hermes_ext.fortune_oracle import core
        for effect in (RuntimeError("engine unavailable"), None):
            with patch("hermes_ext.fortune_oracle.daily_fortune_engine.render_personalized_daily_text",
                       side_effect=effect, return_value=None):
                text = core.render_daily_fortune(profile=PROFILES["A"])
            self.assertIn("태허", text)
            self.assertIn("오락과 자기성찰용", text)

    def test_bridge_failure_returns_none(self):
        with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile",
                   side_effect=RuntimeError("engine unavailable")):
            self.assertIsNone(build_personalized_daily(PROFILES["A"], target_date=T))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestRealKline(unittest.TestCase):
    def test_periods_compute_birth_chart_once(self):
        from hermes_ext.fortune_oracle import bazi_bridge, kline
        for builder, kwargs, count in ((kline.build_monthly_kline, {"year": 2024, "month": 2}, 29),
                                       (kline.build_yearly_kline, {"year": 2024}, 12)):
            with patch.object(bazi_bridge, "calculate_bazi_from_profile",
                              wraps=bazi_bridge.calculate_bazi_from_profile) as calc:
                with patch.object(bazi_bridge.subprocess, "run", wraps=subprocess.run) as node:
                    candles = builder(PROFILES["A"], **kwargs)
            self.assertEqual(len(candles), count)
            self.assertEqual(calc.call_count, 1)
            self.assertEqual(node.call_count, 1)

    def test_daily_close_matches_engine_all_aspects(self):
        from hermes_ext.fortune_oracle import kline
        for aspect in ("종합", "활동", "관계", "재물", "건강"):
            candles = kline.build_monthly_kline(PROFILES["A"], 2026, 10, aspect)
            self.assertEqual(len(candles), 31)
            for candle in (candles[0], candles[-1]):
                today = build_personalized_daily(PROFILES["A"], target_date=candle.date, aspect=aspect)
                yesterday = build_personalized_daily(PROFILES["A"], target_date=candle.date-datetime.timedelta(days=1), aspect=aspect)
                self.assertEqual(candle.close, today["score"])
                self.assertEqual(candle.open, yesterday["score"])
                self.assertEqual(candle.high, max(candle.open, candle.close))
                self.assertEqual(candle.low, min(candle.open, candle.close))
            self.assertTrue(all(a.close == b.open for a, b in zip(candles, candles[1:])))

    def test_yearly_ohlc_aggregates_every_day(self):
        from hermes_ext.fortune_oracle import kline
        months = kline.build_yearly_kline(PROFILES["A"], 2024)
        for month in months:
            days = kline.build_monthly_kline(PROFILES["A"], 2024, month.date.month)
            scores = [c.close for c in days]
            self.assertEqual((month.open, month.close, month.high, month.low),
                             (scores[0], scores[-1], max(scores), min(scores)))

    def test_missing_profile_never_produces_scores(self):
        from hermes_ext.fortune_oracle import kline, core
        for profile in (None, {}, {"display_name": "테스트"}, {"birth_date": "bad"}):
            self.assertIsNone(kline.build_daily_candle(profile))
            self.assertEqual(kline.build_monthly_kline(profile), [])
            self.assertEqual(kline.build_yearly_kline(profile), [])
            self.assertIsNone(core.get_daily_candle_score(profile))
            self.assertIn("생성할 수 없습니다", kline.render_month_kline(profile))
            self.assertIn("생성할 수 없습니다", core.render_kline_card(profile=profile))

    def test_engine_failure_has_no_partial_period(self):
        from hermes_ext.fortune_oracle import kline, core
        with patch("hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile",
                   side_effect=RuntimeError("private birth data")):
            self.assertEqual(kline.build_monthly_kline(PROFILES["A"]), [])
            self.assertIsNone(core.get_daily_candle_score(PROFILES["A"]))
            text = core.render_kline_card(profile=PROFILES["A"])
            self.assertIn("생성할 수 없습니다", text)
            self.assertNotIn("private", text)

    def test_mid_period_failure_discards_whole_period(self):
        from hermes_ext.fortune_oracle import daily_fortune_engine as engine, kline
        original = engine._daily_from_chart
        def fail_on_day(profile, result, target_date, aspect):
            if target_date == datetime.date(2026, 10, 15):
                raise ValueError("invalid calculation")
            return original(profile, result, target_date, aspect)
        with patch.object(engine, "_daily_from_chart", side_effect=fail_on_day):
            self.assertEqual(kline.build_monthly_kline(PROFILES["A"], 2026, 10), [])

    def test_dayun_is_labeled_as_calculated_with_interpretive_adjustment(self):
        from hermes_ext.fortune_oracle import kline
        candles = kline.build_monthly_kline(PROFILES["A"], 2026, 10)
        text = kline.summarize_kline(candles)
        self.assertTrue(candles[-1].dayun_theme)
        self.assertIn("절기 기반 대운", text)
        self.assertIn("해석 보정 반영", text)
        for private in ("1990-05-15", "07:30", "서울"):
            self.assertNotIn(private, text)

class TestCalculatedDayun(unittest.TestCase):
    def test_bridge_matches_library_and_cycles_are_contiguous(self):
        from hermes_ext.fortune_oracle.bazi_bridge import calculate_bazi_from_profile
        result = calculate_bazi_from_profile(PROFILES['A'])
        script = """
const {Solar}=require(process.argv[1]);
// Seoul civil 07:30 = 06:30 in the library's UTC+8 solar-term frame.
const yun=Solar.fromYmdHms(1990,5,15,6,30,0).getLunar().getEightChar().getYun(1,2);
console.log(JSON.stringify({start:yun.getStartSolar().toYmd(),
cycles:yun.getDaYun(13).slice(1).map(c=>[c.getGanZhi(),c.getStartYear(),c.getEndYear()])}));
"""
        expected = json.loads(subprocess.check_output(['node', '-e', script, NODE_LUNAR], text=True))
        self.assertEqual(result.dayun['start_date'], expected['start'])
        self.assertEqual([(c['pillar'], c['start_year'], c['end_year'])
                          for c in result.dayun['cycles']], [tuple(c) for c in expected['cycles']])
        self.assertEqual(result.dayun['start_date'], '1997-09-16')
        cycles = result.dayun['cycles']
        self.assertTrue(all(a['end_year'] + 1 == b['start_year'] for a,b in zip(cycles,cycles[1:])))

    def test_cycle_boundary_changes_score_and_preserves_daily_kline_parity(self):
        from hermes_ext.fortune_oracle import daily_fortune_engine as engine, bazi_bridge, kline
        result = bazi_bridge.calculate_bazi_from_profile(PROFILES['A'])
        for year, expected in ((2006, '壬午'), (2007, '癸未')):
            day = datetime.date(year, 1, 1)
            actual = engine._daily_from_chart(PROFILES['A'], result, day, '종합')
            self.assertEqual(actual['dayun_pillar'], expected)
            self.assertTrue(actual['dayun_adjustment'])
            with patch.object(bazi_bridge, 'calculate_bazi_from_profile', return_value=result):
                candle = kline.build_daily_candle(PROFILES['A'], day)
            self.assertEqual(candle.close, actual['score'])
            no_dayun = bazi_bridge.BaziResult.from_dict({**result.__dict__, 'dayun': None})
            base = engine._daily_from_chart(PROFILES['A'], no_dayun, day, '종합')
            self.assertAlmostEqual(actual['score'], base['score'] + actual['dayun_adjustment'], places=1)

    def test_missing_gender_or_time_does_not_invent_dayun(self):
        from hermes_ext.fortune_oracle import bazi_bridge
        for missing in ('gender', 'birth_time'):
            profile = {k:v for k,v in PROFILES['A'].items() if k != missing}
            result = bazi_bridge.calculate_bazi_from_profile(profile)
            self.assertTrue(result.ok)
            self.assertIsNone(result.dayun)
            reading = build_personalized_daily(profile, target_date=datetime.date(2026,10,1))
            self.assertEqual(reading['dayun_pillar'], '')
            self.assertEqual(reading['dayun_adjustment'], 0)
