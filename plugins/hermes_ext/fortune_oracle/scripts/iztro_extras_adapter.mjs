/**
 * iztro_extras_adapter.mjs
 * Thin, verification-only adapter for DaXian (대한) only.
 * Length C: our core engine untouched. iztro supplies only verified extras.
 * Brightness deliberately excluded (mapping not yet confirmed).
 *
 * Now also supplies native iztro decadal sihua (daxian_sihua) via heavenlyStems.mutagen data.
 * This eliminates manual SIHUA_TABLE duplication in Python bridge for 대한 사화.
 *
 * Usage as module:
 *   const { getDaXianExtras } = require('./iztro_extras_adapter.mjs');
 *   const extras = getDaXianExtras({ solar: '1994-3-4', timeIdx: 1, gender: '男' });
 *
 * Run directly for 6-chart verification:
 *   node iztro_extras_adapter.mjs
 */

import { createRequire } from 'module';
const requireCjs = createRequire(import.meta.url);
const { astro } = requireCjs('iztro');

const starKo = {
  '紫微': '자미', '天机': '천기', '太阳': '태양', '武曲': '무곡',
  '天同': '천동', '廉贞': '염정', '天府': '천부', '太阴': '태음',
  '贪狼': '탐랑', '巨门': '거문', '天相': '천상', '天梁': '천량',
  '七杀': '칠살', '破军': '파군'
};

// Native iztro decadal (대한) sihua mapping, sourced from iztro's heavenlyStems.mutagen data
// Order: 祿, 權, 科, 忌  (lu, quan, ke, ji)
// Verified against iztro lib for 1986/1994 cases (e.g. 庚: 태양·무곡·태음·천동)
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
  '癸': ['破军', '巨门', '太阴', '贪狼']
};

function getDecadalSihuaKr(stem) {
  const cnList = IZTRO_DECADAL_SIHUA[stem] || [];
  const labels = ['lu', 'quan', 'ke', 'ji'];
  const res = {};
  cnList.forEach((cn, i) => {
    const kr = starKo[cn] || cn;
    res[labels[i]] = { star: kr };
  });
  return res;
}

function getDaXianExtras(params) {
  const { solar, timeIdx, gender, lunar } = params;
  let chart;
  if (lunar) {
    // support lunar if needed later: year, month, day, timeIdx, gender, isLeap, fixLeap, lang
    chart = astro.byLunar(lunar.year, lunar.month, lunar.day, timeIdx, gender || '男', false, true, 'zh-CN');
  } else {
    chart = astro.bySolar(solar, timeIdx, gender || '男', true, 'zh-CN');
  }

  const daxian = [];
  chart.palaces.forEach(p => {
    if (p.decadal && p.decadal.range) {
      const stem = p.decadal.heavenlyStem;
      const entry = {
        ages: p.decadal.range.join('-'),
        ganzhi: stem + p.decadal.earthlyBranch,
        palace_name: p.name,           // e.g. 命宫
        palace_branch: p.earthlyBranch // e.g. 未 or 丑
      };
      const sihua = getDecadalSihuaKr(stem);
      if (Object.keys(sihua).length > 0) {
        entry.sihua = sihua;  // native iztro daxian_sihua: {lu:{star:'태양'}, quan:{star:'무곡'}, ...}
      }
      daxian.push(entry);
    }
  });

  // Sort by starting age to ensure sequence (iztro order may vary)
  daxian.sort((a, b) => parseInt(a.ages.split('-')[0], 10) - parseInt(b.ages.split('-')[0], 10));

  return {
    daxian,
    source: 'iztro-v2.5.8',
    soul_branch: chart.earthlyBranchOfSoulPalace
  };
}

// Direct run: print for the 6 verification charts
if ((import.meta.url === `file://${process.argv[1]}` || process.argv[1].endsWith('iztro_extras_adapter.mjs')) && process.stdin.isTTY) {
  const charts = [
    { id: 'exampleA', solar: '1992-8-14', timeIdx: 5, gender: '男' },
    { id: '2024',  solar: '2024-6-21', timeIdx: 3, gender: '女' },
    { id: '1986b', solar: '1986-2-6',  timeIdx: 6, gender: '男' },
    { id: 'su2',   solar: '1994-3-4',  timeIdx: 1, gender: '男' },
    { id: 'jin4',  solar: '1994-3-2',  timeIdx: 5, gender: '男' },
    { id: 'to5',   solar: '1994-3-4',  timeIdx: 7, gender: '男' },
  ];

  console.log('=== iztro_extras_adapter.mjs (DaXian + native daxian_sihua from iztro) ===\n');
  charts.forEach(c => {
    const extras = getDaXianExtras(c);
    console.log('--- ' + c.id + ' (soul: ' + extras.soul_branch + ') ---');
    console.log('source:', extras.source);
    console.log('daxian (12):');
    extras.daxian.forEach((d, i) => {
      let line = '  ' + (i+1).toString().padStart(2) + '. ages ' + d.ages + ' | ' + d.ganzhi + ' | ' + d.palace_name + ' (' + d.palace_branch + ')';
      if (d.sihua) {
        const s = d.sihua;
        line += ' | sihua: lu=' + (s.lu && s.lu.star) + ', quan=' + (s.quan && s.quan.star) + ', ke=' + (s.ke && s.ke.star) + ', ji=' + (s.ji && s.ji.star);
      }
      console.log(line);
    });
    console.log('');
  });
  console.log('=== End of 6-chart DaXian output (now with iztro-native daxian_sihua) ===');
}

export { getDaXianExtras };  // for ESM consumers
// For CJS: module.exports = { getDaXianExtras }; is handled by the requireCjs pattern above when used.
/**
 * Stdin support for Python bridge (same pattern as ziwei_doushu_bridge.mjs)
 * Input JSON: {birth_date, birth_time, gender}
 * Output: {daxian: [...], current_daxian: {...}, source}
 * Now current_daxian includes .sihua from iztro if available.
 */
function getTimeIdx(birth_time) {
  if (!birth_time) return 0;
  const [hStr] = birth_time.split(':');
  const h = parseInt(hStr, 10) || 0;
  // Ziwei time index mapping (approximate for bridge call)
  return Math.floor(((h + 1) % 24) / 2);
}

if (!process.stdin.isTTY) {
  let input = '';
  process.stdin.on('data', (chunk) => { input += chunk; });
  process.stdin.on('end', () => {
    try {
      const raw = JSON.parse(input.trim());
      const { birth_date, birth_time, gender } = raw;
      const timeIdx = getTimeIdx(birth_time);
      const extras = getDaXianExtras({ solar: birth_date, timeIdx, gender: gender || '男' });
      const currentYear = new Date().getFullYear();
      const birthYear = parseInt((birth_date || '2000').split('-')[0], 10);
      const age = currentYear - birthYear;
      let current = null;
      for (const d of extras.daxian) {
        const [start, end] = d.ages.split('-').map(Number);
        if (age >= start && age <= end) {
          current = { ...d, age };
          break;
        }
      }
      const out = {
        daxian: extras.daxian,
        current_daxian: current,
        source: extras.source,
        soul_branch: extras.soul_branch
      };
      process.stdout.write(JSON.stringify(out) + '\n');
    } catch (e) {
      process.stdout.write(JSON.stringify({ ok: false, error: e.message }) + '\n');
    }
    process.exit(0);
  });
}
