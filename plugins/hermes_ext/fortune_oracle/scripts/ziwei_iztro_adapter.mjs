/**
 * ziwei_iztro_adapter.mjs — Direct iztro adapter (병렬 어댑터, 1단계)
 *
 * Purpose: Call iztro bySolar/byLunar directly and output
 * the SAME facts format that ziwei_doushu_bridge.mjs + _enrich_ziwei_facts() produce.
 *
 * Key differences from bridge.mjs:
 * - Uses iztro's built-in brightness, sihua, decadal sihua, body palace, etc.
 * - No separate iztro_extras_adapter call needed
 * - Brightness in majorStars/mutagen directly from iztro
 * - Output normalized to traditional Chinese (번체) to match bridge.mjs format
 *
 * CRITICAL: timeIdx uses hardcoded lookup table — NEVER compute via formula.
 * See: 00:00-00:59=子=0, 01:00-02:59=丑=1, ..., 23:00-23:59=子=0
 *
 * Input JSON (stdin):
 *   {birth_date, birth_time, gender, calendar?, isLeapMonth?, longitude?}
 *
 * Output JSON (stdout): Same structure as bridge.mjs output
 *
 * Policy:
 * - bridge.mjs NOT modified
 * - NOT connected to calculate_ziwei_chart yet (1단계)
 * - stdout JSON only, timeout by Python caller
 */

import { createRequire } from 'module';
const requireCjs = createRequire(import.meta.url);
const { astro } = requireCjs('iztro');

// ============================================================
// HARDCODED timeIdx lookup — NO FORMULA
// ============================================================

const HOUR_TO_TIME_IDX = [
  // 0:00-0:59  = 子時 = timeIdx 0
  0,  // 0
  1,  // 1
  1,  // 2
  2,  // 3
  2,  // 4
  3,  // 5
  3,  // 6
  4,  // 7
  4,  // 8
  5,  // 9
  5,  // 10
  6,  // 11
  6,  // 12
  7,  // 13
  7,  // 14
  8,  // 15
  8,  // 16
  9,  // 17
  9,  // 18
  10, // 19
  10, // 20
  11, // 21
  11, // 22
  0,  // 23  — 晚子时, 子時 = timeIdx 0
];

function getTimeIdx(birth_time) {
  if (!birth_time || birth_time.trim() === '') {
    throw new Error('missing birth_time');
  }
  const [hStr] = birth_time.split(':');
  const h = parseInt(hStr, 10);
  if (isNaN(h) || h < 0 || h > 23) {
    throw new Error(`invalid hour: ${h}`);
  }
  return HOUR_TO_TIME_IDX[h];
}

// ============================================================
// Mapping: simplified → traditional Chinese (for star names)
// ============================================================

const SIMP_TO_TRAD = {
  '紫微': '紫微', '天机': '天機', '太阳': '太陽', '武曲': '武曲',
  '天同': '天同', '廉贞': '廉貞', '天府': '天府', '太阴': '太陰',
  '贪狼': '貪狼', '巨门': '巨門', '天相': '天相', '天梁': '天梁',
  '七杀': '七殺', '破军': '破軍',
  '文昌': '文昌', '文曲': '文曲',
  '火星': '火星', '铃星': '鈴星',
  '擎羊': '擎羊', '陀罗': '陀羅',
  '禄存': '綠存', '天马': '天馬',
  '天魁': '天魁', '天钺': '天鉞',
  '左辅': '左輔', '右弼': '右弼',
  '地空': '地空', '地劫': '地劫',
};

// Mutagen: simplified → traditional
const MUTAGEN_MAP = { '禄': '祿', '权': '權', '科': '科', '忌': '忌' };

// Star Korean mapping (for aux_stars / sihua output matching bridge format)
const STAR_KO = {
  '紫微': '자미', '天機': '천기', '太陽': '태양', '武曲': '무곡',
  '天同': '천동', '廉貞': '염정', '天府': '천부', '太陰': '태음',
  '貪狼': '탐랑', '巨門': '거문', '天相': '천상', '天梁': '천량',
  '七殺': '칠살', '破軍': '파군',
  '文昌': '문창', '文曲': '문곡',
  '火星': '화성', '鈴星': '영성',
  '擎羊': '경양', '陀羅': '타라',
  '綠存': '녹존', '天馬': '천마',
  '天魁': '천괴', '天鉞': '천월',
  '左輔': '좌보', '右弼': '우필',
  '地空': '지공', '地劫': '지겁',
};

// ============================================================
// Branch constants
// ============================================================

// iztro index 0=寅, 1=卯, ... 11=丑
// bridge index 0=子, 1=丑, ... 11=亥
// Conversion: bridgeIdx = (iztroIdx + 2) % 12
const IZTRO_BRANCHES = ['寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥', '子', '丑'];
const BRIDGE_BRANCHES = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];

function iztroIdxToBridge(iztroIdx) {
  return (iztroIdx + 2) % 12;
}

function branchToIztroIdx(branch) {
  const i = IZTRO_BRANCHES.indexOf(branch);
  return i;
}

function branchToBridgeIdx(branch) {
  const i = BRIDGE_BRANCHES.indexOf(branch);
  return i;
}

// ============================================================
// Decadal sihua from iztro's heavenlyStems.mutagen data
// ============================================================

const IZTRO_DECADAL_SIHUA = {
  '甲': ['廉贞', '破军', '武曲', '太阳'],
  '乙': ['天机', '天梁', '紫微', '太阴'],
  '丙': ['天同', '天机', '文昌', '廉贞'],
  '丁': ['太阴', '天同', '天机', '巨门'],
  '戊': ['贪狼', '太阴', '右弼', '天机'],
  '己': ['武曲', '贪狼', '天梁', '文曲'],
  '庚': ['太阳', '武曲', '太阴', '天同'],
  '辛': ['巨门', '太阳', '文曲', '天同'],
  '壬': ['天梁', '紫微', '左辅', '武曲'],
  '癸': ['破军', '巨门', '太阴', '贪狼'],
};

function getDecadalSihua(stem) {
  const cnList = IZTRO_DECADAL_SIHUA[stem] || [];
  const labels = ['lu', 'quan', 'ke', 'ji'];
  const res = {};
  cnList.forEach((cn, i) => {
    const trad = SIMP_TO_TRAD[cn] || cn;
    const ko = STAR_KO[trad] || trad;
    res[labels[i]] = { star: ko };
  });
  return res;
}

// ============================================================
// Five Elements class parsing
// iztro returns "土五局", "火六局" etc.
// ============================================================

function parseWuxingJu(fiveElementsClass) {
  if (!fiveElementsClass) return { ju_number: null, nayin: null, wuxing: null, ju_name: null };
  // e.g. "土五局" → wuxing=土, ju=5
  const wuxing = fiveElementsClass[0];
  // Extract number: 五=5, 六=6, 一=1, etc.
  const cnNumMap = { '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10 };
  let juNumber = null;
  for (const [cn, num] of Object.entries(cnNumMap)) {
    if (fiveElementsClass.includes(cn)) {
      juNumber = num;
      break;
    }
  }
  return {
    ju_number: juNumber,
    nayin: null, // iztro doesn't provide full nayin
    wuxing: wuxing,
    ju_name: fiveElementsClass,
  };
}

// ============================================================
// Main adapter
// ============================================================

function calculateZiwei(params) {
  const { birth_date, birth_time, gender, calendar, isLeapMonth } = params;
  const timeIdx = getTimeIdx(birth_time);
  const g = gender || '男';

  let chart;
  if (calendar === 'lunar') {
    chart = astro.byLunar(birth_date, timeIdx, g, !!isLeapMonth, true, 'zh-CN');
  } else {
    chart = astro.bySolar(birth_date, timeIdx, g, true, 'zh-CN');
  }

  // Find ming_gong palace
  const mingBranch = chart.earthlyBranchOfSoulPalace;
  const mingPalace = chart.palaces.find(p => p.earthlyBranch === mingBranch);
  const mingIdx = branchToBridgeIdx(mingBranch);

  // ============================================================
   // 1. stars — bridge format: index (子=0) → [번체 별 이름]
   //    iztro: index 0=寅 → convert to bridge index
   // ============================================================
   const stars = {};
   chart.palaces.forEach(p => {
     const bridgeIdx = iztroIdxToBridge(p.index);
     const majorStars = p.majorStars
       .filter(s => s.type === 'major')
       .map(s => SIMP_TO_TRAD[s.name] || s.name);
     if (majorStars.length > 0) {
       stars[String(bridgeIdx)] = majorStars;
     }
   });

   // ============================================================
   // 1b. brightness — iztro brightness per star (5-3B)
   //     format: { "idx_star": brightness_cn } (e.g. "0_天機": "旺")
   //     iztro brightness: 庙/旺/得/失/陷 etc. (한자)
   // ============================================================
   const brightness = {};
   chart.palaces.forEach(p => {
     const bridgeIdx = iztroIdxToBridge(p.index);
     p.majorStars.forEach(s => {
       if (s.type === 'major') {
         const trad = SIMP_TO_TRAD[s.name] || s.name;
         // iztro brightness is already in Chinese characters
         if (s.brightness) {
           brightness[`${bridgeIdx}_${trad}`] = s.brightness;
         }
       }
     });
     // Also include minorStars brightness
     p.minorStars.forEach(s => {
       const trad = SIMP_TO_TRAD[s.name] || s.name;
       if (s.brightness) {
         brightness[`${bridgeIdx}_${trad}`] = s.brightness;
       }
     });
   });

   // ============================================================
   // 2. aux_stars — Korean name → 번체 지지
  // ============================================================
  const auxStars = {};
  chart.palaces.forEach(p => {
    p.minorStars.forEach(s => {
      const trad = SIMP_TO_TRAD[s.name] || s.name;
      const ko = STAR_KO[trad];
      if (ko && ko !== trad) {
        auxStars[ko] = p.earthlyBranch;
      }
    });
  });

  // ============================================================
  // 3. sihua — raw 祿/權/科/忌 format (bridge format)
  // ============================================================
  const sihua = {};
  chart.palaces.forEach(p => {
    // 文昌/文曲 and 左輔/右弼 can carry mutagen values in minorStars.
    // Preserve actual engine entries from both collections.
    [...(p.majorStars || []), ...(p.minorStars || [])].forEach(s => {
      if (s.mutagen) {
        const tradStar = SIMP_TO_TRAD[s.name] || s.name;
        const tradMut = MUTAGEN_MAP[s.mutagen] || s.mutagen;
        const bridgeIdx = iztroIdxToBridge(p.index);
        sihua[tradMut] = {
          star: tradStar,
          palace_index: bridgeIdx,
        };
      }
    });
  });

  // ============================================================
  // 4. ming_gong
  // ============================================================
  const mingGong = {
    branch: mingBranch,
    index: mingIdx,
  };

  // ============================================================
  // 5. wuxing_ju
  // ============================================================
  const wuxingJuData = parseWuxingJu(chart.fiveElementsClass);
  const wuxingJu = {
    ju_number: wuxingJuData.ju_number,
    nayin: wuxingJuData.nayin,
    wuxing: wuxingJuData.wuxing,
    ju_name: wuxingJuData.ju_name,
    ming_gong_ganzhi: mingPalace ? (mingPalace.heavenlyStem + mingBranch) : null,
  };

  // ============================================================
  // 6. ziwei_info
  // ============================================================
  let ziweiBranch = null;
  let ziweiIzIdx = null;
  chart.palaces.forEach(p => {
    if (p.majorStars.some(s => (SIMP_TO_TRAD[s.name] || s.name) === '紫微')) {
      ziweiBranch = p.earthlyBranch;
      ziweiIzIdx = p.index;
    }
  });
  const ziweiInfo = {
    position: ziweiIzIdx !== null ? iztroIdxToBridge(ziweiIzIdx) : null,
    branch: ziweiBranch,
    source: 'iztro',
  };

  // ============================================================
  // 7. tianfu
  // ============================================================
  let tianfuBranch = null;
  let tianfuIzIdx = null;
  chart.palaces.forEach(p => {
    if (p.majorStars.some(s => (SIMP_TO_TRAD[s.name] || s.name) === '天府')) {
      tianfuBranch = p.earthlyBranch;
      tianfuIzIdx = p.index;
    }
  });

  // ============================================================
  // 8. solar / lunar info
  // ============================================================
  // Parse solar date from chart.solarDate (e.g. "1994-3-4")
  const solar = (() => {
    if (!chart.solarDate) return null;
    const parts = chart.solarDate.split('-');
    return {
      year: parseInt(parts[0], 10),
      month: parseInt(parts[1], 10),
      day: parseInt(parts[2], 10),
    };
  })();

  // Parse raw lunar from chart.rawDates
  const lunar = (() => {
    try {
      if (chart.rawDates && chart.rawDates.lunarDate) {
        const ld = chart.rawDates.lunarDate;
        return {
          year: ld.lunarYear,
          month: ld.lunarMonth,
          day: ld.lunarDay,
          isLeap: ld.isLeap || false,
        };
      }
    } catch (_) {}
    return null;
  })();

  // ============================================================
  // 9. year_ganzhi — from iztro's chineseDate (not solar year)
  // ============================================================
  const yearGanzhi = (() => {
    if (chart.rawDates && chart.rawDates.chineseDate && chart.rawDates.chineseDate.yearly) {
      return chart.rawDates.chineseDate.yearly.join('');
    }
    // Fallback: solar year calculation (less accurate near year boundary)
    if (!solar) return null;
    const stems = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸'];
    const branches = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];
    return stems[(solar.year - 4) % 10] + branches[(solar.year - 4) % 12];
  })();

  const yearStem = yearGanzhi ? yearGanzhi[0] : null;

  // ============================================================
  // 10. Decadal sihua (대한 사화) — NEW iztro data
  // ============================================================
  const decadalSihua = {};
  chart.palaces.forEach(p => {
    if (p.decadal && p.decadal.heavenlyStem) {
      const stem = p.decadal.heavenlyStem;
      const sihuaData = getDecadalSihua(stem);
      if (Object.keys(sihuaData).length > 0) {
        const bridgeIdx = iztroIdxToBridge(p.index);
        decadalSihua[bridgeIdx] = {
          stem,
          branch: p.earthlyBranch,
          ganzhi: stem + p.earthlyBranch,
          sihua: sihuaData,
        };
      }
    }
  });

  // ============================================================
  // 11. Body palace (신궁) — NEW
  // ============================================================
  const bodyPalace = chart.earthlyBranchOfBodyPalace || null;

  // ============================================================
  // 12. Heavenly stems per palace — NEW
  // ============================================================
  const palaceStems = {};
  chart.palaces.forEach(p => {
    const bridgeIdx = iztroIdxToBridge(p.index);
    palaceStems[String(bridgeIdx)] = p.heavenlyStem;
  });

  // ============================================================
  // 13. 十二长生 per palace — NEW
  // ============================================================
  const changsheng12 = {};
  chart.palaces.forEach(p => {
    if (p.changsheng12) {
      const bridgeIdx = iztroIdxToBridge(p.index);
      changsheng12[String(bridgeIdx)] = p.changsheng12;
    }
  });

  // ============================================================
  // 14. 大限 (decadal) info — NEW
  // ============================================================
  const daxian = [];
  chart.palaces.forEach(p => {
    if (p.decadal && p.decadal.range) {
      const bridgeIdx = iztroIdxToBridge(p.index);
      daxian.push({
        index: bridgeIdx,
        branch: p.earthlyBranch,
        stem: p.decadal.heavenlyStem,
        branch_decadal: p.decadal.earthlyBranch,
        ganzhi: p.decadal.heavenlyStem + p.decadal.earthlyBranch,
        range: p.decadal.range,
        ages: p.ages || [],
        palace_name: p.name,
      });
    }
  });

  // Sort by starting age
  daxian.sort((a, b) => (a.range && b.range ? a.range[0] - b.range[0] : 0));

  // ============================================================
  // Build output
  // ============================================================
  return {
    ok: true,
    engine: 'ziwei-iztro-adapter',
    calendar: calendar || 'solar',
    input: { birth_date, birth_time, gender: g },
    solar,
    lunar,
    year_ganzhi: yearGanzhi,
    year_stem: yearStem,
    ming_gong: mingGong,
    wuxing_ju: wuxingJu,
    ziwei_info: ziweiInfo,
    tianfu_position: tianfuIzIdx !== null ? iztroIdxToBridge(tianfuIzIdx) : null,
    tianfu_branch: tianfuBranch,
    stars,
    brightness,
    aux_stars: auxStars,
    sihua,
    // NEW: iztro-exclusive data (not in bridge.mjs)
    body_palace: bodyPalace,
    decadal_sihua: decadalSihua,
    palace_stems: palaceStems,
    changsheng12: changsheng12,
    daxian,
    disclaimer: '이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.',
    warnings: [],
  };
}

// ============================================================
// Unit tests for timeIdx
// ============================================================

function runTimeIdxTests() {
  const tests = [
    { time: '00:00', expected: 0 },
    { time: '02:00', expected: 1 },
    { time: '04:00', expected: 2 },
    { time: '12:00', expected: 6 },
    { time: '14:00', expected: 7 },
    { time: '22:00', expected: 11 },
    { time: '23:00', expected: 0 },
    { time: '23:30', expected: 0 },
  ];
  let pass = 0, fail = 0;
  tests.forEach(t => {
    const actual = getTimeIdx(t.time);
    if (actual === t.expected) {
      pass++;
    } else {
      fail++;
      console.error(`  FAIL: ${t.time} → ${actual} (expected ${t.expected})`);
    }
  });
  return { pass, fail };
}

// ============================================================
// Direct run: standalone test (to5 chart)
// ============================================================

if (process.argv[1] && process.argv[1].endsWith('ziwei_iztro_adapter.mjs') && process.stdin.isTTY) {
  console.log('=== ziwei_iztro_adapter.mjs standalone test ===\n');

  // Unit test: timeIdx
  console.log('--- Unit test: timeIdx ---');
  const timeIdxResult = runTimeIdxTests();
  console.log(`  timeIdx tests: ${timeIdxResult.pass} pass, ${timeIdxResult.fail} fail`);
  if (timeIdxResult.fail > 0) {
    console.error('  CRITICAL: timeIdx tests failed — aborting');
    process.exit(1);
  }

  // Test 1: to5 (양력)
  console.log('\n--- Test 1: to5 (양력 1994-03-04 22:00 male) ---');
  const result1 = calculateZiwei({
    birth_date: '1994-03-04',
    birth_time: '22:00',
    gender: '男',
  });
  console.log(JSON.stringify(result1, null, 2));

  // Test 2: to5 (음력) — same chart via lunar path
  console.log('\n--- Test 2: to5 (음력 1994-01-23 22:00 male) ---');
  const result2 = calculateZiwei({
    birth_date: '1994-1-23',
    birth_time: '22:00',
    gender: '男',
    calendar: 'lunar',
    isLeapMonth: false,
  });
  console.log(JSON.stringify(result2, null, 2));

  // Test 3: 1986b
  console.log('\n--- Test 3: 1986b (1986-02-06 12:00 male) ---');
  const result3 = calculateZiwei({
    birth_date: '1986-02-06',
    birth_time: '12:00',
    gender: '男',
  });
  console.log(JSON.stringify(result3, null, 2));

  console.log('\n=== All tests complete ===');
} else if (!process.stdin.isTTY) {
  // Stdin interface
  let input = '';
  process.stdin.on('data', (chunk) => { input += chunk; });
  process.stdin.on('end', () => {
    try {
      const raw = JSON.parse(input.trim());
      const result = calculateZiwei(raw);
      process.stdout.write(JSON.stringify(result) + '\n');
    } catch (e) {
      process.stdout.write(JSON.stringify({
        ok: false,
        error_code: 'ENGINE_ERROR',
        message: 'iztro adapter error: ' + e.message,
        warnings: [e.message],
        stars: {},
        ming_gong: {},
        sihua: {},
      }) + '\n');
    }
    process.exit(0);
  });
}

export { calculateZiwei };
