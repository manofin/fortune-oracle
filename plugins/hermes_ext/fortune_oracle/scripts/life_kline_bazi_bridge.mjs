/**
 * life_kline_bazi_bridge.mjs — Bazi/八字 계산 Node CLI sandbox bridge
 *
 * 입력: stdin JSON
 * 출력: stdout JSON only
 * debug/log: stderr only
 *
 * 금지:
 *   - stdout에 JSON 외 텍스트 출력
 *   - 외부 네트워크 호출
 *   - 파일 시스템 쓰기
 *   - 서버 실행
 *   - AI/LLM 호출
 *
 * 이 결과는 오락과 자기성찰 용도이며
 * 의학, 투자, 법률 결정을 지시하지 않습니다.
 */

import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const require = createRequire(import.meta.url);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fail(error_code, message, warnings = []) {
  process.stdout.write(
    JSON.stringify({ ok: false, error_code, message, warnings }) + "\n"
  );
  process.exit(0);
}

function dbg(...args) {
  process.stderr.write("[bazi_bridge] " + args.join(" ") + "\n");
}

// ---------------------------------------------------------------------------
// Input validation
// ---------------------------------------------------------------------------

function validateInput(raw) {
  if (!raw || typeof raw !== "object") {
    return { valid: false, code: "INVALID_INPUT", message: "입력이 객체가 아닙니다." };
  }

  const { birth_date, birth_time } = raw;

  if (!birth_date || typeof birth_date !== "string") {
    return { valid: false, code: "INVALID_INPUT", message: "birth_date 필드가 없거나 문자열이 아닙니다." };
  }
  const dateMatch = birth_date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!dateMatch) {
    return {
      valid: false, code: "INVALID_INPUT",
      message: `birth_date 형식 오류: '${birth_date}'. YYYY-MM-DD 형식이어야 합니다.`,
    };
  }
  const [, yStr, mStr, dStr] = dateMatch;
  const year = parseInt(yStr, 10);
  const month = parseInt(mStr, 10);
  const day = parseInt(dStr, 10);

  if (year < 1800 || year > 2100) {
    return { valid: false, code: "UNSUPPORTED_DATE", message: `지원 범위(1800-2100) 외 연도: ${year}` };
  }
  if (month < 1 || month > 12) {
    return { valid: false, code: "INVALID_INPUT", message: `잘못된 월: ${month}` };
  }
  if (day < 1 || day > 31) {
    return { valid: false, code: "INVALID_INPUT", message: `잘못된 일: ${day}` };
  }

  // birth_time: HH:MM (optional)
  let hour = 0, minute = 0;
  if (birth_time) {
    if (typeof birth_time !== "string") {
      return { valid: false, code: "INVALID_INPUT", message: "birth_time이 문자열이 아닙니다." };
    }
    const timeMatch = birth_time.match(/^(\d{1,2}):(\d{2})$/);
    if (!timeMatch) {
      return {
        valid: false, code: "INVALID_INPUT",
        message: `birth_time 형식 오류: '${birth_time}'. HH:MM 형식이어야 합니다.`,
      };
    }
    hour = parseInt(timeMatch[1], 10);
    minute = parseInt(timeMatch[2], 10);
    if (hour > 23 || minute > 59) {
      return { valid: false, code: "INVALID_INPUT", message: `잘못된 시간: ${birth_time}` };
    }
  }

  return { valid: true, year, month, day, hour, minute };
}

// ---------------------------------------------------------------------------
// 오행 테이블
// ---------------------------------------------------------------------------

const HEAVENLY_STEMS = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"];
const EARTHLY_BRANCHES = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"];

const STEM_ELEMENT = {
  "甲":"木","乙":"木","丙":"火","丁":"火","戊":"土",
  "己":"土","庚":"金","辛":"金","壬":"水","癸":"水",
};
const BRANCH_ELEMENT = {
  "子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火",
  "午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水",
};
const ELEMENT_KR = { "木":"목(木)","火":"화(火)","土":"토(土)","金":"금(金)","水":"수(水)" };
const ZODIAC_KR = ["쥐","소","호랑이","토끼","용","뱀","말","양","원숭이","닭","개","돼지"];

function countElements(chars4) {
  const count = { "木":0,"火":0,"土":0,"金":0,"水":0 };
  for (const gz of chars4) {
    if (gz && gz.length >= 2) {
      const stem = gz[0], branch = gz[1];
      if (STEM_ELEMENT[stem]) count[STEM_ELEMENT[stem]]++;
      if (BRANCH_ELEMENT[branch]) count[BRANCH_ELEMENT[branch]]++;
    }
  }
  return count;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  // 1. stdin 읽기
  let rawInput = "";
  for await (const chunk of process.stdin) {
    rawInput += chunk;
    if (rawInput.length > 4096) {
      fail("INVALID_INPUT", "입력 JSON이 너무 큽니다 (4096바이트 초과).");
    }
  }

  let parsed;
  try {
    parsed = JSON.parse(rawInput.trim());
  } catch (e) {
    fail("INVALID_INPUT", `JSON 파싱 실패: ${e.message}`);
  }

  // 2. 검증
  const validation = validateInput(parsed);
  if (!validation.valid) {
    fail(validation.code, validation.message);
  }
  const { year, month, day, hour, minute } = validation;
  const warnings = [];

  // 3. lunar-javascript 로드
  let Solar, LunarTime;
  try {
    const lj = require(path.join(__dirname, "node_modules", "lunar-javascript"));
    Solar = lj.Solar;
    LunarTime = lj.LunarTime;
    dbg("lunar-javascript loaded OK");
  } catch (e) {
    dbg("load error:", e.message);
    fail("DEPENDENCY_MISSING", `lunar-javascript 로드 실패: ${e.message}`);
  }

  // 4. Solar → Lunar 변환
  let solarObj, lunarObj;
  try {
    solarObj = Solar.fromYmd(year, month, day);
    lunarObj = solarObj.getLunar();
    dbg(`lunar: ${lunarObj.getYear()}-${lunarObj.getMonth()}-${lunarObj.getDay()}`);
  } catch (e) {
    dbg("Solar/Lunar error:", e.message);
    fail("ENGINE_ERROR", `날짜 변환 오류: ${e.message}`);
  }

  // Solar-term tables are returned in UTC+8 (qiAccurate's ONE_THIRD day).
  // Keep civil day/hour pillars separate from the physical term instant.
  let termSolar = solarObj;
  if (parsed.term_reference) {
    const r = parsed.term_reference;
    termSolar = Solar.fromYmdHms(r.year, r.month, r.day, r.hour, r.minute, r.second);
  }
  const termLunar = termSolar.getLunar();
  const termCandidates = parsed.term_interval ? parsed.term_interval.map(r =>
    Solar.fromYmdHms(r.year, r.month, r.day, r.hour, r.minute, r.second).getLunar()) : [];
  const yearCandidates = [...new Set(termCandidates.map(l => l.getYearInGanZhiExact()))];
  const monthCandidates = [...new Set(termCandidates.map(l => l.getMonthInGanZhiExact()))];
  const uncertainPillars = [];
  if (yearCandidates.length > 1) uncertainPillars.push("year");
  if (monthCandidates.length > 1) uncertainPillars.push("month");
  warnings.push(parsed.birth_time_known === false
    ? "일주는 출생지 민간 날짜 기준이며 경도·진태양시 보정은 적용하지 않았습니다."
    : "일·시주는 출생지 민간시 기준이며 경도·진태양시 보정은 적용하지 않았습니다.");
  if (!parsed.term_reference && (!parsed.term_interval || uncertainPillars.length)) {
    warnings.push("절기 비교의 출생 순간이 미확정 — 절기 경계의 년·월주와 대운은 불확실합니다.");
  }

  // 5. 사주 팔자 계산 — Lunar 인스턴스 직접 간지 접근
  let eightChar;
  try {
    // 년주/월주/일주 — Lunar 인스턴스에서 직접 간지 접근
    // FORTUNE_BAZI_SOLAR_TERM_MONTH=1 이면 절기 시각 기준 Exact 버전 사용
    const useExact = Boolean(parsed.term_reference) || process.env.FORTUNE_BAZI_SOLAR_TERM_MONTH === '1';
    const yearGanZhi = parsed.term_interval ? (yearCandidates.length === 1 ? yearCandidates[0] : "") : useExact
      ? termLunar.getYearInGanZhiExact()
      : lunarObj.getYearInGanZhi();
    const monthGanZhi = parsed.term_interval ? (monthCandidates.length === 1 ? monthCandidates[0] : "") : useExact
      ? termLunar.getMonthInGanZhiExact()
      : lunarObj.getMonthInGanZhi();
    const dayGanZhi = lunarObj.getDayInGanZhi();

    // 시주 — LunarTime.fromYmdHms 사용 후 getGanZhi()
    const lt = LunarTime.fromYmdHms(
      lunarObj.getYear(), lunarObj.getMonth(), lunarObj.getDay(),
      hour, minute, 0
    );
    const timeGanZhi = parsed.birth_time_known === false ? "" : lt.getGanZhi();

    eightChar = {
      year: yearGanZhi,
      month: monthGanZhi,
      day: dayGanZhi,
      time: timeGanZhi,
    };
    dbg("eight_char:", JSON.stringify(eightChar));
  } catch (e) {
    dbg("EightChar error:", e.message);
    fail("ENGINE_ERROR", `팔자 계산 오류: ${e.message}`);
  }

  // 6. 오행 분석
  const elementCount = countElements([
    eightChar.year, eightChar.month, eightChar.day, eightChar.time,
  ]);
  const elements = {};
  for (const [k, v] of Object.entries(elementCount)) {
    if (v > 0) elements[ELEMENT_KR[k] || k] = v;
  }

  // 7. 띠 계산 (입춘 기준이 아닌 음력 년도 기준)
  const lunarYear = lunarObj.getYear();
  const zodiacIdx = ((lunarYear - 4) % 12 + 12) % 12;
  const zodiac = ZODIAC_KR[zodiacIdx] + "띠";

  // 8. 음력 윤달 여부 — getLeapMonth() 는 없음, getMonth()가 음수면 윤달
  // lunar-javascript에서 윤달은 month가 음수로 표현됨
  const rawLunarMonth = lunarObj.getMonth();
  const isLeap = rawLunarMonth < 0;
  const absMonth = Math.abs(rawLunarMonth);
  const lunarMonthStr = isLeap ? `윤${absMonth}월` : `${absMonth}월`;

  // 절기 기반 기운(sect 2: 분 단위 환산). 구간은 라이브러리의 연도 기준.
  // 출생시각/전통 성별 입력이 없으면 임의 추정하지 않는다.
  let dayun = null;
  const gender = String(parsed.gender || "").trim().toLowerCase();
  const male = ["male", "m", "남", "남성"].includes(gender);
  const female = ["female", "f", "여", "여성"].includes(gender);
  if ((male || female) && parsed.birth_time_known !== false && parsed.birth_time) {
    try {
      const birth = parsed.term_reference ? termSolar : Solar.fromYmdHms(year, month, day, hour, minute, 0);
      const yun = birth.getLunar().getEightChar().getYun(male ? 1 : 0, 2);
      dayun = {
        backend: "lunar-javascript", sect: 2, interval_mode: "calendar_year",
        direction: yun.isForward() ? "forward" : "reverse",
        start_date: yun.getStartSolar().toYmd(),
        start_reference: parsed.term_reference ? yun.getStartSolar().toYmdHms() : null,
        cycles: yun.getDaYun(13).filter(c => c.getIndex() > 0).map(c => ({
          pillar: c.getGanZhi(), start_year: c.getStartYear(), end_year: c.getEndYear(),
        })),
      };
    } catch (e) {
      warnings.push("절기 기반 대운 계산 실패 — 대운 보정 생략");
    }
  }

  // 9. 결과
  const solarTermMode = parsed.term_interval ? !uncertainPillars.length :
    Boolean(parsed.term_reference) || process.env.FORTUNE_BAZI_SOLAR_TERM_MONTH === '1';
  const result = {
    ok: true,
    engine: "lunar-javascript",
    solar_term_month_mode: solarTermMode,
    time_basis: {solar_terms: parsed.term_reference ? "birth_instant_utc_plus_8" :
                   parsed.term_interval && !uncertainPillars.length ? "civil_day_interval_confirmed" : "date_only_uncertain",
                 uncertain_pillars: uncertainPillars,
                 pillar_candidates: parsed.term_interval ? {year: yearCandidates, month: monthCandidates} : {},
                 day_hour: "local_civil_time", day_boundary: "midnight", true_solar_time: false,
                 hour_convention: "lunar_javascript_LunarTime", dayun: "sect_2_calendar_year_local"},
    input: {
      birth_date: parsed.birth_date,
      birth_time: parsed.birth_time || "00:00",
      birth_place: parsed.birth_place || "",
      timezone: parsed.timezone || "Asia/Seoul",
      gender: parsed.gender || "unknown",
    },
    solar: { year, month, day, hour, minute },
    lunar: {
      year: lunarYear,
      month: absMonth,
      month_str: lunarMonthStr,
      day: lunarObj.getDay(),
      is_leap: isLeap,
    },
    eight_char: eightChar,
    elements,
    zodiac,
    dayun,
    disclaimer: "이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.",
    warnings,
  };

  process.stdout.write(JSON.stringify(result) + "\n");
}

main().catch((e) => {
  dbg("Unhandled:", e.message);
  fail("ENGINE_ERROR", `예상치 못한 오류: ${e.message}`);
});
