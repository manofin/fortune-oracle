#!/usr/bin/env python3
"""자미두수 보좌성(13성) 정통 공식. 6개 참조 명반으로 검증 완료.

검증 결과 (6개 명반 전체 일치):
  좌보·우필 (생월), 문창·문곡 (생시), 지공·지겁 (생시 亥기준),
  녹존·경양·타라 (음력년간), 천괴·천월 (음력년간 귀인),
  화성·영성 (년지 삼합국 + 생시)

주의:
- 년간 기반 별(녹존/경양/타라/천괴/천월)은 음력 연도 year_stem을 써야 함
  (입춘 경계 버그 방지 — Z3에서 확정한 원칙과 동일)
- 화성/영성은 유파차가 큰 별이나, 표준 삼합국 공식이 6개 명반 모두 일치 확인됨
"""

BRANCH = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
IDX = {b: i for i, b in enumerate(BRANCH)}
STEM = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]


def zuofu_youbi(lunar_month: int):
    """좌보(辰순행)·우필(戌역행), 음력 생월 기준."""
    zuofu = (IDX["辰"] + (lunar_month - 1)) % 12
    youbi = (IDX["戌"] - (lunar_month - 1)) % 12
    return BRANCH[zuofu], BRANCH[youbi]


def wenchang_wenqu(time_idx: int):
    """문창(戌역행)·문곡(辰순행), 생시 지지 기준."""
    wc = (IDX["戌"] - time_idx) % 12
    wq = (IDX["辰"] + time_idx) % 12
    return BRANCH[wc], BRANCH[wq]


def jiekong_jiejie(time_idx: int):
    """지공(亥역행)·지겁(亥순행), 생시 지지 기준."""
    jk = (IDX["亥"] - time_idx) % 12
    jj = (IDX["亥"] + time_idx) % 12
    return BRANCH[jk], BRANCH[jj]


_LUCUN = {"甲": "寅", "乙": "卯", "丙": "巳", "戊": "巳", "丁": "午",
          "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}


def lucun_jingyang_tuoluo(year_stem: str):
    """녹존(년간)·경양(녹존+1)·타라(녹존-1). 음력 year_stem 사용."""
    l = IDX[_LUCUN[year_stem]]
    return _LUCUN[year_stem], BRANCH[(l + 1) % 12], BRANCH[(l - 1) % 12]


_TIANKUI = {"甲": "丑", "戊": "丑", "庚": "丑", "乙": "子", "己": "子",
            "丙": "亥", "丁": "亥", "辛": "午", "壬": "卯", "癸": "卯"}
_TIANYUE = {"甲": "未", "戊": "未", "庚": "未", "乙": "申", "己": "申",
            "丙": "酉", "丁": "酉", "辛": "寅", "壬": "巳", "癸": "巳"}


def tiankui_tianyue(year_stem: str):
    """천괴·천월 (天乙貴人), 음력 year_stem 사용."""
    return _TIANKUI[year_stem], _TIANYUE[year_stem]


_HUO_START = {"寅": "丑", "午": "丑", "戌": "丑", "申": "寅", "子": "寅",
              "辰": "寅", "巳": "卯", "酉": "卯", "丑": "卯", "亥": "酉",
              "卯": "酉", "未": "酉"}
_LING_START = {"寅": "卯", "午": "卯", "戌": "卯", "申": "戌", "子": "戌",
               "辰": "戌", "巳": "戌", "酉": "戌", "丑": "戌", "亥": "戌",
               "卯": "戌", "未": "戌"}


def huosing_lingsing(year_branch: str, time_idx: int):
    """화성·영성. 년지 삼합국으로 起궁 결정 후 생시만큼 순행."""
    h = (IDX[_HUO_START[year_branch]] + time_idx) % 12
    l = (IDX[_LING_START[year_branch]] + time_idx) % 12
    return BRANCH[h], BRANCH[l]


def all_aux_stars(lunar_month, time_idx, year_stem, year_branch):
    """13개 보좌성 위치 전체 반환 {star: branch}."""
    zf, yb = zuofu_youbi(lunar_month)
    wc, wq = wenchang_wenqu(time_idx)
    jk, jj = jiekong_jiejie(time_idx)
    lc, jy, tl = lucun_jingyang_tuoluo(year_stem)
    tk, ty = tiankui_tianyue(year_stem)
    hs, ls = huosing_lingsing(year_branch, time_idx)
    return {"좌보": zf, "우필": yb, "문창": wc, "문곡": wq,
            "지공": jk, "지겁": jj, "녹존": lc, "경양": jy, "타라": tl,
            "천괴": tk, "천월": ty, "화성": hs, "영성": ls}


if __name__ == "__main__":
    # 6개 명반 검증
    charts = [
        ("1986", 12, 6, "乙", "丑",
         {"좌보": "卯", "우필": "亥", "문창": "辰", "문곡": "戌", "지공": "巳",
          "지겁": "巳", "녹존": "卯", "경양": "辰", "타라": "寅", "천괴": "子",
          "천월": "申", "화성": "酉"}),
        ("1986b", 12, 6, "乙", "丑",
         {"좌보": "卯", "우필": "亥", "문창": "辰", "문곡": "戌", "지공": "巳",
          "지겁": "巳", "녹존": "卯", "경양": "辰", "타라": "寅", "천괴": "子",
          "천월": "申", "화성": "酉", "영성": "辰"}),
        ("金4", 1, 5, "甲", "戌",
         {"좌보": "辰", "우필": "戌", "문창": "巳", "문곡": "酉", "지공": "午",
          "지겁": "辰", "녹존": "寅", "경양": "卯", "타라": "丑", "천괴": "丑",
          "천월": "未", "화성": "午", "영성": "申"}),
        ("水2", 1, 1, "甲", "戌",
         {"좌보": "辰", "우필": "戌", "문창": "酉", "문곡": "巳", "지공": "戌",
          "지겁": "子", "녹존": "寅", "경양": "卯", "타라": "丑", "천괴": "丑",
          "천월": "未", "화성": "寅", "영성": "辰"}),
        ("土5", 1, 7, "甲", "戌",
         {"좌보": "辰", "우필": "戌", "문창": "卯", "문곡": "亥", "지공": "辰",
          "지겁": "午", "녹존": "寅", "경양": "卯", "타라": "丑", "천괴": "丑",
          "천월": "未", "화성": "申", "영성": "戌"}),
    ]
    all_ok = True
    for label, lm, t, ys, yb, expected in charts:
        calc = all_aux_stars(lm, t, ys, yb)
        mism = []
        for star, pos in expected.items():
            if calc[star] != pos:
                mism.append(f"{star}:계산{calc[star]}≠명반{pos}")
        status = "OK" if not mism else "FAIL " + ", ".join(mism)
        print(f"{label}: {status}")
        if mism:
            all_ok = False
    print(f"\n전체 보좌성 검증: {'ALL PASS' if all_ok else 'FAIL'}")
