/**
 * ziwei_doushu_bridge.mjs — Ziwei Doushu (安星法) Step 1-3 Bridge
 *
 * DEPRECATED (4단계): 운영 경로에서 ziwei_iztro_adapter.mjs로 전환됨.
 * 롤백용 유지 — 삭제 금지.
 *
 * Step 1-1: solar-to-lunar conversion + Ming Gong (命宮)
 * Step 1-2: 紫微星 위치 + 십사주성(十四主星) 배치
 * Step 1-3: 사화(四化) 배분 (祿/權/科/忌)
 *
 * 출력: stdout JSON only
 * 에러: fail-open {ok:false, error_code, message}
 *
 * 금지: stdout에 JSON 외 텍스트, 외부 네트워크, 파일 쓰기, 서버 실행, LLM 호출
 * 의존: lunar-javascript (node_modules)
 *
 * 命宮 계산식 (安星法 simplified):
 *   1. 寅宮 (index 2) 기준에서 시작
 *   2. 생월(lunarMonth)만큼順行
 *   3. 생시 지장간(earthly branch of the hour) 기준 寅宮과의 차이만큼 逆行
 *   逆 = modulo 12 subtraction
 *
 * 紫微星 위치 + 14성 배치 (simplified 安星法):
 *   - 자미 위치 = (명궁인덱스 + (음력 일 % 12)) % 12
 *   - 나머지 13성은 자미 기준 상대 오프셋으로 배치
 *   ※ 실제 안성법은 일간지(日干) + 월지 + 절기 등에 따라 달라지므로
 *     본 스텝에서는 "음력 일"만을 사용한 단순화 버전으로 검증용으로 사용.
 *
 * 사화(四化) 배분 (안성법 기준):
 *   - 년간(年干)에 따라 化祿/化權/化科/化忌 대상 별이 결정됨
 *   - 본 테이블은 일반적인 안성法 규정을 따름 (文昌/文曲/左輔/右弼 등 보조성은 14성에 없어 null 처리)
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
  process.stderr.write("[ziwei_bridge] " + args.join(" ") + "\n");
}

// ---------------------------------------------------------------------------
// Input validation (life_kline_bazi_bridge.mjs pattern)
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
  const year = parseInt(dateMatch[1], 10);
  const month = parseInt(dateMatch[2], 10);
  const day = parseInt(dateMatch[3], 10);

  if (year < 1800 || year > 2100) {
    return { valid: false, code: "UNSUPPORTED_DATE", message: `지원 범위(1800-2100) 외 연도: ${year}` };
  }
  if (month < 1 || month > 12) {
    return { valid: false, code: "INVALID_INPUT", message: `잘못된 월: ${month}` };
  }
  if (day < 1 || day > 31) {
    return { valid: false, code: "INVALID_INPUT", message: `잘못된 일: ${day}` };
  }

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
// Ziwei constants / helpers
// ---------------------------------------------------------------------------

const EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"];
const YIN_INDEX = 2; // 寅宮 시작점 (0-indexed)

// 14성 정의 (자미 기준 상대 배치 순서)
const MAIN_STARS = ["紫微", "天機", "太陽", "武曲", "天同", "廉貞", "天府", "太陰", "貪狼", "巨門", "天相", "天梁", "七殺", "破軍"];
const MAIN_STAR_OFFSETS = [0, 1, 2, 3, 4, 5, 6, -2, -3, -4, 7, -1, -5, -6];

// 사화(四化) 배분표 (安星法, 년간 甲~癸 순서)
const SIHUA_TABLE = [
  { 祿: "廉貞", 權: "破軍", 科: "武曲", 忌: "太陽" },  // 甲
  { 祿: "天機", 權: "天梁", 科: "紫微", 忌: "太陰" },  // 乙
  { 祿: "天同", 權: "天機", 科: "文昌", 忌: "廉貞" },  // 丙
  { 祿: "太陰", 權: "天同", 科: "天機", 忌: "巨門" },  // 丁
  { 祿: "貪狼", 權: "太陰", 科: "右弼", 忌: "天機" },  // 戊
  { 祿: "武曲", 權: "貪狼", 科: "天梁", 忌: "文曲" },  // 己
  { 祿: "太陽", 權: "武曲", 科: "太陰", 忌: "天同" },  // 庚
  { 祿: "巨門", 權: "太陽", 科: "文曲", 忌: "天同" },  // 辛
  { 祿: "天梁", 權: "紫微", 科: "左輔", 忌: "武曲" },  // 壬
  { 祿: "破軍", 權: "巨門", 科: "太陰", 忌: "貪狼" },  // 癸
];

const STEMS = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"];
const STEM_IDX = {"甲":0,"乙":1,"丙":2,"丁":3,"戊":4,"己":5,"庚":6,"辛":7,"壬":8,"癸":9};

// 五虎遁: 년간 → 寅월의 천간
const WUHU_DUN = {
  "甲": "丙", "己": "丙",
  "乙": "戊", "庚": "戊",
  "丙": "庚", "辛": "庚",
  "丁": "壬", "壬": "壬",
  "戊": "甲", "癸": "甲",
};

// 60갑자 納音五行 (오행국 계산용)
const NAYIN = [
  ["甲子","海中金"], ["乙丑","海中金"],
  ["丙寅","爐中火"], ["丁卯","爐中火"],
  ["戊辰","大林木"], ["己巳","大林木"],
  ["庚午","路旁土"], ["辛未","路旁土"],
  ["壬申","劍鋒金"], ["癸酉","劍鋒金"],
  ["甲戌","山頭火"], ["乙亥","山頭火"],
  ["丙子","澗下水"], ["丁丑","澗下水"],
  ["戊寅","城頭土"], ["己卯","城頭土"],
  ["庚辰","白臘金"], ["辛巳","白臘金"],
  ["壬午","楊柳木"], ["癸未","楊柳木"],
  ["甲申","泉中水"], ["乙酉","泉中水"],
  ["丙戌","屋上土"], ["丁亥","屋上土"],
  ["戊子","霹靂火"], ["己丑","霹靂火"],
  ["庚寅","松柏木"], ["辛卯","松柏木"],
  ["壬辰","長流水"], ["癸巳","長流水"],
  ["甲午","沙中金"], ["乙未","沙中金"],
  ["丙申","山下火"], ["丁酉","山下火"],
  ["戊戌","平地木"], ["己亥","平地木"],
  ["庚子","壁上土"], ["辛丑","壁上土"],
  ["壬寅","金箔金"], ["癸卯","金箔金"],
  ["甲辰","覆燈火"], ["乙巳","覆燈火"],
  ["丙午","天河水"], ["丁未","天河水"],
  ["戊申","大驛土"], ["己酉","大驛土"],
  ["庚戌","釵釧金"], ["辛亥","釵釧金"],
  ["壬子","桑柘木"], ["癸丑","桑柘木"],
  ["甲寅","大溪水"], ["乙卯","大溪水"],
  ["丙辰","沙中土"], ["丁巳","沙中土"],
  ["戊午","天上火"], ["己未","天上火"],
  ["庚申","石榴木"], ["辛酉","石榴木"],
  ["壬戌","大海水"], ["癸亥","大海水"],
];
const NAYIN_MAP = Object.fromEntries(NAYIN);
// 오행국 매핑: 水二局=2, 木三국=3, 金四국=4, 土五국=5, 火六국=6
const WUXING_JU_MAP = { "水": 2, "木": 3, "金": 4, "土": 5, "火": 6 };
const WUXING_JU_NAMES = { 2: "水二局", 3: "木三국", 4: "金四국", 5: "土五국", 6: "火六국" };



function getTimeBranchIndex(hour, minute) {
  if (hour === 23 || hour < 1) return 0;
  const idx = Math.floor((hour + 1) / 2) % 12;
  return idx;
}

// Step 1-1: Ming Gong (정통 안성법)
// 1. 寅宮(2)에서 lunarMonth만큼 순행 → 월의 위치
// 2. 그 위치에서 생시(地支)만큼 逆行 → 명궁
function calculateMingGong(lunarMonth, hour, minute) {
  const timeBranchIndex = getTimeBranchIndex(hour, minute);
  // 1. 寅(2)에서 lunarMonth만큼 순행
  const monthPos = (YIN_INDEX + (lunarMonth - 1)) % 12;
  // 2. 그 위치에서 시간지지만큼 역행
  const mingPos = (monthPos - timeBranchIndex + 12) % 12;
  return {
    branch: EARTHLY_BRANCHES[mingPos],
    index: mingPos,
    formula: {
      lunar_month: lunarMonth,
      time_branch_index: timeBranchIndex,
      time_branch: EARTHLY_BRANCHES[timeBranchIndex],
      yin_index: YIN_INDEX,
    },
  };
}

// ---------------------------------------------------------------------------
// Gate Z3: 정통 起紫微訣 (자미성 위치) — ziwei_star_placement.py 와 100% 일치
// 검증 근거: 
//   1. 5국 1일 기준점 (水2=丑, 木3=辰, 金4=亥, 土5=午, 火6=酉) — 교재 표준
//   2. 실제 명반 6개 (5개 오행국 전체: 木3×2, 火6, 水2, 金4, 土5)
//   3. ziwei_star_placement.py locate_ziwei() 와 완전 동일 알고리즘
// ---------------------------------------------------------------------------

// 14정성 정의 (한어) — Z1 검증 공식 유지 (자미系 역행 / 천부系 순행)
const ZIWEI_XI = [["天機",-1],["太陽",-3],["武曲",-4],["天同",-5],["廉貞",-8]];  // 자미系 역행
const TIANFU_XI = [["太陰",1],["貪狼",2],["巨門",3],["天相",4],["天梁",5],["七殺",6],["破軍",10]]; // 천부系 순행

// 정통 起紫微訣 (Python locate_ziwei와 1:1)
// remainder = lunarDay % ju
// add = (remainder == 0) ? 0 : ju - remainder
// quotient = Math.floor((lunarDay + add) / ju)
// base = YIN_INDEX(2) + (quotient - 1)
// pos = (add % 2 === 0 ? base + add : base - add) % 12 (음수 보정)
function locateZiwei(lunarDay, juNumber) {
  const remainder = lunarDay % juNumber;
  let add, quotient;
  if (remainder === 0) {
    quotient = Math.floor(lunarDay / juNumber);
    add = 0;
  } else {
    add = juNumber - remainder;
    quotient = Math.floor((lunarDay + add) / juNumber);
  }
  const base = YIN_INDEX + (quotient - 1);
  let pos = (add % 2 === 0) ? (base + add) : (base - add);
  pos = ((pos % 12) + 12) % 12;  // 안전한 modulo (음수 대응)
  return {
    position: pos,
    branch: EARTHLY_BRANCHES[pos],
    add: add,                    // 부족분 (검증/디버그용)
    lunar_day: lunarDay,
    ju_number: juNumber,
    source: "authentic"          // 정통 알고리즘 (table 자기참조 제거)
  };
}

// 천부 위치 = (4 - 자미idx) % 12 (검증 완료). JS 음수 나머지 보정.
function tianfuFromZiwei(ziweiIdx) {
  return ((4 - ziweiIdx) % 12 + 12) % 12;
}

// 정통 안성법 14정성 전체 배치
function buildStarPalacesTraditional(lunarDay, juNumber) {
  // 자미 위치
  const ziweiInfo = locateZiwei(lunarDay, juNumber);
  const ziweiPos = ziweiInfo.position;

  // 천부 위치
  const tianfuPos = tianfuFromZiwei(ziweiPos);

  // palaceMap: 12궁 각각의 별 목록
  const palaceMap = new Array(12).fill(null).map(() => []);

  // 자미
  palaceMap[ziweiPos].push("紫微");

  // 자미系 (역행)
  for (const [star, off] of ZIWEI_XI) {
    const target = (ziweiPos + off + 12) % 12;
    palaceMap[target].push(star);
  }

  // 천부
  palaceMap[tianfuPos].push("天府");

  // 천부系 (순행)
  for (const [star, off] of TIANFU_XI) {
    const target = (tianfuPos + off + 12) % 12;
    palaceMap[target].push(star);
  }

  const stars = {};
  for (let idx = 0; idx < 12; idx++) {
    if (palaceMap[idx].length > 0) {
      stars[idx] = palaceMap[idx];
    }
  }

  return {
    stars,
    ziwei_info: ziweiInfo,
    tianfu_position: tianfuPos,
    tianfu_branch: EARTHLY_BRANCHES[tianfuPos],
  };
}

// ---------------------------------------------------------------------------
// Gate Z4: 보좌성 (輔佐星) 계산 — 정통 安星法
// ---------------------------------------------------------------------------

// Z4-1: 좌보·우필 (음력 생월), 문창·문곡·지공·지겁 (생시)
// lunarMonth: 1~12 (음력월)
// timeBranchIndex: getTimeBranchIndex 결과 (0=子 ... 11=亥)
// Returns Korean branch names
// Z4-1 + Z4-2: 보좌성
// lunarMonth, timeBranchIndex, lunarYearStem (음력 year stem, e.g. "乙")
// ---------------------------------------------------------------------------
// Gate Z4: 보좌성 (13성) — 정통 安星法 (6개 명반 검증 완료)
// ---------------------------------------------------------------------------

// 년간 → 녹존 궁 (정통 표)
const LU_CUN_MAP = {
  "甲": "寅", "乙": "卯",
  "丙": "巳", "戊": "巳",
  "丁": "午", "己": "午",
  "庚": "申", "辛": "酉",
  "壬": "亥", "癸": "子"
};

// 년간 → 천괴/천월 (귀인 표, 정통)
const GUI_REN_MAP = {
  "甲": ["丑", "未"], "戊": ["丑", "未"], "庚": ["丑", "未"],
  "乙": ["子", "申"], "己": ["子", "申"],
  "丙": ["亥", "酉"], "丁": ["亥", "酉"],
  "辛": ["午", "寅"],
  "壬": ["卯", "巳"], "癸": ["卯", "巳"]
};

// 년지 삼합 → 화성/영성 起궁 (정통 삼합국 공식)
const HUO_LING_START = {
  "寅": "丑", "午": "丑", "戌": "丑",   // 寅午戌
  "申": "寅", "子": "寅", "辰": "寅",   // 申子辰
  "巳": "卯", "酉": "卯", "丑": "卯",   // 巳酉丑
  "亥": "酉", "卯": "酉", "未": "酉"    // 亥卯未
};

function calculateAuxStars(lunarMonth, timeBranchIndex, lunarYearStem, lunarYearBranch) {
  const aux = {};

  // === Z4-1: 생월/생시 기반 ===
  const monthOffset = (lunarMonth - 1 + 12) % 12;

  // 좌보: 辰(4) + (월-1) 순행
  aux["좌보"] = EARTHLY_BRANCHES[(4 + monthOffset) % 12];

  // 우필: 戌(10) - (월-1) 역행
  aux["우필"] = EARTHLY_BRANCHES[(10 - monthOffset + 12) % 12];

  // 문창: 戌(10) - 생시 역행
  aux["문창"] = EARTHLY_BRANCHES[(10 - timeBranchIndex + 12) % 12];

  // 문곡: 辰(4) + 생시 순행
  aux["문곡"] = EARTHLY_BRANCHES[(4 + timeBranchIndex) % 12];

  // 지겁: 亥(11) + 생시 순행   (정통)
  aux["지겁"] = EARTHLY_BRANCHES[(11 + timeBranchIndex) % 12];

  // 지공: 亥(11) - 생시 역행   (정통)
  aux["지공"] = EARTHLY_BRANCHES[(11 - timeBranchIndex + 12) % 12];

  // === Z4-2: 년간 기반 (녹존·경양·타라) — lunarYearStem 필수 ===
  const lucun = LU_CUN_MAP[lunarYearStem] || "寅";
  const lucunIdx = EARTHLY_BRANCHES.indexOf(lucun);
  aux["녹존"] = lucun;
  aux["경양"] = EARTHLY_BRANCHES[(lucunIdx + 1) % 12];
  aux["타라"] = EARTHLY_BRANCHES[(lucunIdx - 1 + 12) % 12];

  // === Z4-3: 천괴·천월 (년간 귀인) — lunarYearStem ===
  const gui = GUI_REN_MAP[lunarYearStem] || ["丑", "未"];
  aux["천괴"] = gui[0];
  aux["천월"] = gui[1];

  // === Z4-4: 화성·영성 (년지 삼합 + 생시) — lunarYearBranch 필수 ===
  const huoStart = HUO_LING_START[lunarYearBranch] || "丑";
  const huoIdx = EARTHLY_BRANCHES.indexOf(huoStart);
  // 화성: 起궁에서 생시 순행
  aux["화성"] = EARTHLY_BRANCHES[(huoIdx + timeBranchIndex) % 12];

  // 영성: 起궁 (대부분 戌, 특정 삼합은 卯)
  let lingStart = "戌";
  if (["寅", "午", "戌"].includes(lunarYearBranch)) lingStart = "卯";
  else if (["申", "子", "辰"].includes(lunarYearBranch)) lingStart = "戌";
  else if (["巳", "酉", "丑"].includes(lunarYearBranch)) lingStart = "戌";
  else lingStart = "戌";  // default

  const lingIdx = EARTHLY_BRANCHES.indexOf(lingStart);
  aux["영성"] = EARTHLY_BRANCHES[(lingIdx + timeBranchIndex) % 12];

  return aux;
}

// ---------------------------------------------------------------------------
// Gate Z2: 오행국(五行局) 계산
// ---------------------------------------------------------------------------

// 명궁 간지 계산: 년간 → 五虎遁 → 명궁 천간 도출
function calcMingGongGanzhi(yearStem, mingGongBranch) {
  const yinTianGan = WUHU_DUN[yearStem];
  const yinIdx = EARTHLY_BRANCHES.indexOf("寅"); // 2
  const mingIdx = EARTHLY_BRANCHES.indexOf(mingGongBranch);
  const offset = (mingIdx - yinIdx + 12) % 12;
  const mingTianGanIdx = (STEM_IDX[yinTianGan] + offset) % 10;
  const mingTianGan = STEMS[mingTianGanIdx];
  return mingTianGan + mingGongBranch;
}

// 納音五行에서 오행 추출
function getNayinWuxing(nayinName) {
  for (const w of ["金", "木", "水", "火", "土"]) {
    if (nayinName.includes(w)) return w;
  }
  return null;
}

// 명궁 간지에서 오행국 결정
function calcWuxingJu(mingGongGanzhi) {
  const nayin = NAYIN_MAP[mingGongGanzhi];
  if (!nayin) {
    // Fallback for edge cases (e.g. certain young child ming_gong_ganzhi not in partial NAYIN list)
    // Allows chart to proceed with default 水二局; full NAYIN completion recommended later
    return {
      ju_number: 2,
      nayin: 'fallback',
      wuxing: '水',
      ju_name: '水二局 (fallback)',
    };
  }
  const wuxing = getNayinWuxing(nayin);
  const ju = WUXING_JU_MAP[wuxing];
  return {
    ju_number: ju,
    nayin: nayin,
    wuxing: wuxing,
    ju_name: WUXING_JU_NAMES[ju] || `不明${ju}국`,
  };
}

// 전체 오행국 계산 (년간 + 명궁 지지 → 오행국)
function calcWuxingJuFromInput(yearStem, mingGongBranch) {
  const mingGongGanzhi = calcMingGongGanzhi(yearStem, mingGongBranch);
  const ju = calcWuxingJu(mingGongGanzhi);
  return {
    ...ju,
    ming_gong_ganzhi: mingGongGanzhi,
  };
}

// Step 1-3: 사화(四化) 배분
function getYearStemIndex(year) {
  // 甲=0 기준 (4년 = 갑자년)
  return ((year - 4) % 10 + 10) % 10;
}

function buildSihua(stars, yearStemIndex) {
  const table = SIHUA_TABLE[yearStemIndex];
  if (!table) return {};

  const result = {};
  for (const hua of ["祿", "權", "科", "忌"]) {
    const starName = table[hua];
    let palaceIndex = null;
    for (const [idx, list] of Object.entries(stars)) {
      if (list.includes(starName)) {
        palaceIndex = parseInt(idx, 10);
        break;
      }
    }
    result[hua] = { star: starName, palace_index: palaceIndex };
  }
  return result;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
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

  const validation = validateInput(parsed);
  if (!validation.valid) {
    fail(validation.code, validation.message);
  }
  const { year, month, day, hour, minute } = validation;
  const warnings = [];

  // Load lunar-javascript
  let Solar;
let Lunar;
  try {
    const lj = require(path.join(__dirname, "node_modules", "lunar-javascript"));
    Solar = lj.Solar;
    Lunar = lj.Lunar;
    dbg("lunar-javascript loaded OK");
  } catch (e) {
    dbg("load error:", e.message);
    fail("DEPENDENCY_MISSING", `lunar-javascript 로드 실패: ${e.message}`);
  }

  // Solar -> Lunar (or Lunar -> Solar if calendar is 'lunar')
   let solarObj, lunarObj;
   try {
     if (parsed.calendar === "lunar") {
       // 음력 입력: 음력 날짜로 Lunar 객체 생성 후 Solar로 변환
       // 윤달 플래그: isLeapMonth=true이면 음력 월에 -를 붙여 Lunar.fromYmd에 전달
       // (lunar-javascript: 음수 월 = 윤달)
       const leapFlag = parsed.isLeapMonth === true ? -1 : 1;
       lunarObj = Lunar.fromYmd(year, month * leapFlag, day);
       solarObj = lunarObj.getSolar();
       dbg(`lunar: ${lunarObj.getYear()}-${lunarObj.getMonth()}-${lunarObj.getDay()} -> solar: ${solarObj.getYear()}-${solarObj.getMonth()}-${solarObj.getDay()} (isLeapMonth=${parsed.isLeapMonth})`);
     } else {
       // 양력 입력 (기본): 양력 날짜로 Solar 객체 생성 후 Lunar로 변환
       // calendar != 'lunar'이면 절대 음력 변환 경로에 진입하지 않음
       solarObj = Solar.fromYmd(year, month, day);
       lunarObj = solarObj.getLunar();
       dbg(`lunar: ${lunarObj.getYear()}-${lunarObj.getMonth()}-${lunarObj.getDay()}`);
     }
   } catch (e) {
     dbg("Solar/Lunar error:", e.message);
   }

  const rawLunarMonth = lunarObj.getMonth();
  const isLeap = rawLunarMonth < 0;
  const lunarMonth = Math.abs(rawLunarMonth);
  const lunarDay = lunarObj.getDay();
  const lunarYear = lunarObj.getYear();

  // EightChar (팔자) — 년간 추출
  const eightChar = lunarObj.getEightChar();
  const yearGanzhi = eightChar.getYear();  // e.g. "乙丑" (Bazi/Li Chun based, for reference only)
  const yearStem = yearGanzhi.charAt(0);   // e.g. "乙"
  dbg(`year_ganzhi: ${yearGanzhi}, year_stem: ${yearStem} (from EightChar)`);

  // Ming Gong
  const mingGong = calculateMingGong(lunarMonth, hour, minute);

  // Gate Z2: 오행국 계산 — 安星法에서는 음력 연도 기준 year stem 사용 (五虎遁)
  // lunar-javascript의 getEightChar()는 입춘(Li Chun) 기준으로 year stem을 줄 수 있어
  // 1986-02-06 (음력 1985-12-28) 같은 경계에서 丙을 주지만, 자미두수 정통은 음력 연도(乙)를 사용.
  const lunarYearStemIndex = getYearStemIndex(lunarYear);
  const lunarYearStem = STEMS[lunarYearStemIndex];
  const wuxingJu = calcWuxingJuFromInput(lunarYearStem, mingGong.branch);
  dbg(`wuxing_ju: ${JSON.stringify(wuxingJu)} (used lunarYearStem=${lunarYearStem} from lunarYear=${lunarYear})`);

  // Gate Z3: 정통 안성법 14정성 배치
  const starResult = buildStarPalacesTraditional(lunarDay, wuxingJu.ju_number);
  const stars = starResult.stars;
  dbg(`ziwei: ${JSON.stringify(starResult.ziwei_info)}`);
  dbg(`tianfu: ${starResult.tianfu_branch} (idx=${starResult.tianfu_position})`);

  // Gate Z4: 보좌성 13성 (전부 정통 공식)
  const timeBranchIndex = getTimeBranchIndex(hour, minute);
  // lunarYearBranch for 화성·영성 (삼합국). Use simple cycle consistent with lunarYear
  const lunarYearBranchIdx = ((lunarYear - 4) % 12 + 12) % 12;
  const lunarYearBranch = EARTHLY_BRANCHES[lunarYearBranchIdx];
  const auxStars = calculateAuxStars(lunarMonth, timeBranchIndex, lunarYearStem, lunarYearBranch);
  dbg(`aux_stars: ${JSON.stringify(auxStars)}`);

  // Step 1-3: Sihua (四化)
  const yearStemIndex = getYearStemIndex(lunarYear);
  const sihua = buildSihua(stars, yearStemIndex);

  const result = {
    ok: true,
    engine: "ziwei-doushu-traditional",
    calendar: parsed.calendar || "solar",
    input: {
      birth_date: parsed.birth_date,
      birth_time: parsed.birth_time || "00:00",
      gender: parsed.gender || "unknown",
    },
    solar: { year, month, day },
    lunar: {
      year: lunarYear,
      month: lunarMonth,
      day: lunarDay,
      isLeap,
    },
    year_ganzhi: yearGanzhi,
    year_stem: yearStem,
    ming_gong: mingGong,
    wuxing_ju: wuxingJu,
    ziwei_info: starResult.ziwei_info,
    tianfu_position: starResult.tianfu_position,
    tianfu_branch: starResult.tianfu_branch,
    stars,
    aux_stars: auxStars,
    sihua,
    disclaimer: "이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.",
    warnings,
  };

  process.stdout.write(JSON.stringify(result) + "\n");
}

main().catch((e) => {
  dbg("Unhandled:", e.message);
  fail("ENGINE_ERROR", `예상치 못한 오류: ${e.message}`);
});
