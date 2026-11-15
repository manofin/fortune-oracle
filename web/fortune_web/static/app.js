"use strict";
const $ = id => document.getElementById(id);
const integratedEnabled = document.body.dataset.integratedEnabled === "true";
const birthLocationEnabled = document.body.dataset.birthLocationEnabled === "true";
// Read only an allowlisted marker. Never send/store the full URL or referrer.
const entryMarkers = new URLSearchParams(location.search).getAll("from");
const sharedEntry = entryMarkers.length === 1 && entryMarkers[0] === "card";
let entryMeasured = false;
if (location.search) history.replaceState(history.state, "", location.pathname + location.hash);
let csrf = "", profile = null, generation = 0, pending = new AbortController(), deleting = false;
let sessionReady = false, sessionInitialization = null, saving = false, busyState = false;
let shareSource = null, shareFile = null, shareVersion = 0, dateAvailable = false, formStartedDay = "";
let pendingDatedGeneration = null;
const downloadUrls = new Set();
let integratedReport = null, integratedPages = [], integratedPage = 0, integratedShareVersion = 0;
const integratedUrls = new Set();
const API_REQUEST_TIMEOUT_MS = 15000, EVENT_REQUEST_TIMEOUT_MS = 8000;
const PREMIUM_THEMES = new Set(["relationships", "resources", "career", "study", "western", "ziwei"]);
const premiumConfirmed = new Set(), premiumRequests = new Map();
let premiumDay = "", premiumGeneration = 0;
function premiumDayKey() {
  return new Intl.DateTimeFormat("en-CA", {timeZone:"Asia/Seoul", year:"numeric", month:"2-digit", day:"2-digit"}).format(new Date());
}
function updatePremiumButtons() {
  document.querySelectorAll("[data-premium-interest]").forEach(button => {
    const theme = button.dataset.premiumInterest, waiting = premiumRequests.has(theme);
    const confirmed = premiumConfirmed.has(theme);
    button.disabled = waiting;
    button.dataset.confirmed = String(confirmed);
    button.setAttribute("aria-busy", String(waiting));
    button.textContent = waiting ? "기록 중…" : confirmed ? "관심 보냈어요" : "관심 있어요";
    button.setAttribute("aria-label", `${button.closest(".premium-card").querySelector("h4").textContent} ${button.textContent}`);
  });
}
async function withRequestTimeout(operation, signal = null, timeoutMs = API_REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener("abort", cancel, {once:true});
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try { return await operation(controller.signal); }
  catch (err) {
    if (!timedOut || err.name !== "AbortError") throw err;
    const timeout = new Error("응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.");
    timeout.name = "TimeoutError"; throw timeout;
  } finally {
    clearTimeout(timer); signal?.removeEventListener("abort", cancel);
  }
}
function clearPremiumRequests() {
  ++premiumGeneration;
  premiumRequests.forEach(request => request.controller.abort());
  premiumRequests.clear();
}
function clearPremiumMessages() {
  document.querySelectorAll(".premium-status").forEach(status => { status.textContent = ""; delete status.dataset.state; });
}
function hidePremiumInterest(forget = false) {
  clearPremiumRequests(); $("premium-interest").hidden = true; clearPremiumMessages();
  if (forget) { premiumConfirmed.clear(); premiumDay = ""; }
  updatePremiumButtons();
}
function refreshPremiumDay() {
  const day = premiumDayKey();
  if (day === premiumDay) return;
  clearPremiumRequests(); premiumConfirmed.clear(); premiumDay = day;
  clearPremiumMessages(); updatePremiumButtons();
}
function showPremiumInterest() {
  if (!profile || deleting) return;
  refreshPremiumDay(); updatePremiumButtons(); $("premium-interest").hidden = false;
}
async function recordPremiumInterest(button) {
  const theme = button.dataset.premiumInterest;
  if (!PREMIUM_THEMES.has(theme) || !profile || !csrf || deleting || $("premium-interest").hidden) return;
  refreshPremiumDay();
  if (premiumRequests.has(theme)) return;
  const status = $(`premium-status-${theme}`);
  if (premiumConfirmed.has(theme)) {
    status.textContent = "오늘 이 주제에 관심을 보냈어요. 하루 한 번만 집계해요.";
    status.dataset.state = "confirmed"; return;
  }
  const mine = premiumGeneration, owner = profile, day = premiumDay;
  const request = {controller:new AbortController()};
  premiumRequests.set(theme, request);
  status.textContent = "관심을 기록하고 있어요…"; delete status.dataset.state; updatePremiumButtons();
  const current = () => mine === premiumGeneration && owner === profile && !deleting && premiumRequests.get(theme) === request;
  try {
    // This is a user action, so only a confirmed write is presented as recorded.
    // Separate from reading requests; view changes explicitly abort it below.
    const {response, acknowledgement} = await withRequestTimeout(async requestSignal => {
      const response = await fetch("/api/events", {method:"POST", credentials:"same-origin", signal:requestSignal,
        headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf}, body:JSON.stringify({event:"premium_interest", view:theme})});
      return {response, acknowledgement:await response.json()};
    }, request.controller.signal, EVENT_REQUEST_TIMEOUT_MS);
    if (!current()) return;
    if (response.status !== 202 || !acknowledgement || acknowledgement.ok !== true) throw new Error("interest_unconfirmed");
    if (day !== premiumDayKey()) {
      refreshPremiumDay(); status.textContent = "날짜가 바뀌었어요. 오늘의 관심을 다시 선택해 주세요."; return;
    }
    premiumConfirmed.add(theme); status.dataset.state = "confirmed";
    status.textContent = "관심을 기록했어요. 알림은 발송되지 않아요.";
  } catch (err) {
    if (!current()) return;
    status.dataset.state = "error";
    status.textContent = err.name === "TimeoutError"
      ? "응답이 늦어 기록 여부를 확인하지 못했어요. 잠시 후 다시 눌러 주세요."
      : "관심을 기록했는지 확인하지 못했어요. 잠시 후 다시 눌러 주세요.";
  } finally {
    if (premiumRequests.get(theme) === request) { premiumRequests.delete(theme); updatePremiumButtons(); }
  }
}
function clearIntegrated(resetReport = true) {
  ++integratedShareVersion; integratedPages = []; integratedPage = 0;
  $("integrated-share-dialog").close(); $("integrated-share-canvas").width = 0;
  $("integrated-share-canvas").hidden = true; $("integrated-share-placeholder").hidden = false;
  $("integrated-share-canvas").setAttribute("aria-label", "통합 성향 리포트 이미지");
  ["download-integrated-share", "integrated-page-prev", "integrated-page-next"].forEach(id => $(id).disabled = true);
  $("integrated-page-number").textContent = ""; $("integrated-share-status").textContent = "";
  integratedUrls.forEach(url => URL.revokeObjectURL(url)); integratedUrls.clear();
  if (resetReport) {
    integratedReport = null; $("integrated-result").hidden = true;
    ["integrated-methods", "integrated-summary", "integrated-themes", "integrated-evidence", "integrated-limitations", "integrated-text"].forEach(id => $(id).replaceChildren());
    $("integrated-title").textContent = "여러 관점으로 읽는 나";
    $("open-integrated-share").disabled = true;
  }
}
function clearShare() {
  ++shareVersion; shareSource = null; shareFile = null;
  $("share-dialog").close(); $("share-canvas").width = 0; $("share-canvas").hidden = true;
  $("share-canvas").setAttribute("aria-label", "날짜, 세 키워드와 해석 지수를 담은 공유 카드");
  $("share-placeholder").hidden = false; $("share-dialog").dataset.nativeShare = "false";
  $("download-share").disabled = true; $("native-share").hidden = true;
  downloadUrls.forEach(url => URL.revokeObjectURL(url)); downloadUrls.clear();
}
function cancelPending() { pending.abort(); pending = new AbortController(); pendingDatedGeneration = null; hidePremiumInterest(); return ++generation; }
function measure(event, view) {
  if (!csrf) return;
  // Independent of reading cancellation; a revoked session rejects late events server-side.
  withRequestTimeout(requestSignal => fetch("/api/events", {method:"POST", credentials:"same-origin", signal:requestSignal,
    headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf}, body:JSON.stringify({event, view})}),
    null, EVENT_REQUEST_TIMEOUT_MS).catch(() => {});
}
function showError(id, message) { $(id).textContent = message; $(id).hidden = !message; }
// Display only: colour each stem/branch by its 오행. The server computes the pillars; this never changes them.
const ELEMENT_CLASS = {목:"wood", 화:"fire", 토:"earth", 금:"metal", 수:"water"};
const STEMS = [["甲","갑","목"],["乙","을","목"],["丙","병","화"],["丁","정","화"],["戊","무","토"],["己","기","토"],["庚","경","금"],["辛","신","금"],["壬","임","수"],["癸","계","수"]];
const BRANCHES = [["子","자","수"],["丑","축","토"],["寅","인","목"],["卯","묘","목"],["辰","진","토"],["巳","사","화"],["午","오","화"],["未","미","토"],["申","신","금"],["酉","유","금"],["戌","술","토"],["亥","해","수"]];
const TZ_LABEL = {"Asia/Seoul":"한국 시간", "Asia/Tokyo":"일본 시간", "America/New_York":"미국 동부 시간", "America/Los_Angeles":"미국 서부 시간", "Europe/London":"영국 시간"};
function glyph(char, table) {
  const row = table.find(r => r[0] === char || r[1] === char);
  return row && {han:row[0], ko:row[1], element:row[2]};
}
function pillarGlyphs(text) {
  // Accepts 庚午 or 병자. Anything else (미산출, partial values) is shown as plain text.
  const chars = Array.from(text || "");
  if (chars.length !== 2) return null;
  const stem = glyph(chars[0], STEMS), branch = glyph(chars[1], BRANCHES);
  return stem && branch ? [stem, branch] : null;
}
function tile(g) {
  // Inline-level tiles keep the pillar's innerText contiguous (e.g. "丁卯"); the reading lives in a pseudo-element.
  const span = document.createElement("span");
  span.className = `ch ${ELEMENT_CLASS[g.element]}`; span.dataset.read = `${g.ko} · ${g.element}`; span.textContent = g.han;
  return span;
}
function koreanDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${m}월 ${d}일 (${"일월화수목금토"[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]})`;
}
function syncSaveButton() {
  $("save-button").disabled = busyState || saving || deleting || (!sessionReady && !!sessionInitialization);
}
function busy(value) {
  busyState = value;
  $("loading").hidden = !value;
  ["open-share", "date-submit", "compat-submit"].forEach(id => $(id).disabled = value);
  $("date-submit").disabled = value || !dateAvailable;
  $("open-integrated-share").disabled = value || !integratedReport;
  document.querySelectorAll("[data-view]").forEach(b => b.disabled = value);
  syncSaveButton();
}
async function api(path, options = {}) {
  const {signal = pending.signal, ...requestOptions} = options;
  return withRequestTimeout(async requestSignal => {
    const response = await fetch(path, {credentials:"same-origin", ...requestOptions, signal:requestSignal,
      headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf, ...(requestOptions.headers || {})}});
    let data;
    try { data = await response.json(); }
    catch (err) {
      if (err.name === "AbortError") throw err;
      throw new Error("응답을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.");
    }
    if (!response.ok) throw new Error(data.text || "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    return data;
  }, signal);
}
function empty() {
  monthResizeObserver?.disconnect(); monthResizeObserver = null;
  clearShare(); clearIntegrated(); hidePremiumInterest(true);
  clearDailySections();
  $("reading-panel").hidden = true; $("empty-state").hidden = false; document.body.dataset.state = "empty";
  $("reading-title").textContent = "나의 하루"; $("reading-date").textContent = ""; $("reading-date").removeAttribute("datetime");
  ["full-text", "month-text", "keywords", "day-relation", "score", "pillars", "element-bars", "day-pillar", "reading-date-label", "reading-timezone", "chart-warning", "kline-chart", "compat-text", "status"].forEach(id => $(id).replaceChildren());
  ["daily-result", "month-result", "chart-section", "compat-result"].forEach(id => $(id).hidden = true);
  $("compat-form").reset(); $("partner-time").disabled = true; $("date-form").reset();
  showError("reading-error", "");
}
function fillForm(value) {
  $("display-name").value = value.display_name || ""; $("birth-date").value = value.birth_date;
  $("birth-time").value = value.birth_time || ""; $("unknown-time").checked = !value.birth_time;
  $("birth-time").disabled = !value.birth_time; $("birth-zone").value = TZ_LABEL[value.timezone] || value.timezone;
  $("gender").value = value.gender;
  if (birthLocationEnabled) {
    $("birthplace-text").value = value.birthplace_text || "";
    $("birth-latitude").value = value.latitude ?? ""; $("birth-longitude").value = value.longitude ?? "";
  }
}
async function bootstrap() {
  if (sessionInitialization) return sessionInitialization;
  sessionReady = false;
  const controller = new AbortController();
  const initialization = (async () => {
    const data = await api("/api/session", {signal:controller.signal}); csrf = data.csrf; profile = data.profile;
    sessionReady = true;
    if (sharedEntry && !entryMeasured) { entryMeasured = true; measure("shared_link_visit", "card"); }
    setReadingWindow(data.reading_window);
    if (profile) { fillForm(profile); await loadView("today"); } else empty();
  })();
  sessionInitialization = initialization;
  syncSaveButton();
  try { await initialization; }
  catch (err) { if (!sessionReady) csrf = ""; throw err; }
  finally {
    if (sessionInitialization === initialization) sessionInitialization = null;
    syncSaveButton();
  }
}
function setReadingWindow(window) {
  // An older API can still serve daily readings; do not guess its date capabilities.
  dateAvailable = !!(window && /^\d{4}-\d{2}-\d{2}$/.test(window.min) && /^\d{4}-\d{2}-\d{2}$/.test(window.max));
  $("target-date").disabled = !dateAvailable; $("date-submit").disabled = !dateAvailable;
  if (!dateAvailable) { $("date-zone").textContent = "날짜 선택 기능을 확인하지 못했습니다. 오늘·내일 풀이는 계속 볼 수 있습니다."; return; }
  $("target-date").min = window.min; $("target-date").max = window.max;
  if (!$("target-date").value || $("target-date").value < window.min || $("target-date").value > window.max) $("target-date").value = window.min;
  $("date-zone").textContent = `${TZ_LABEL[window.timezone] || window.timezone} 기준 오늘부터 365일 이내를 볼 수 있습니다.`;
}
function drawDaily(result, view) {
  const reading = result.reading;
  // Some engine results have five keywords. Keep the full set in the detailed reading.
  const keywords = reading.keywords.slice(0, 3);
  $("keyword-title").textContent = view === "tomorrow" ? "내일을 바라보는 키워드" : view === "dday" ? "그날을 준비하는 키워드" : "오늘을 바라보는 키워드";
  $("reading-date").textContent = result.date; $("reading-date").dateTime = result.date;
  $("reading-date-label").textContent = `${result.date.slice(0, 4)}년 ${koreanDate(result.date)}`;
  $("reading-timezone").textContent = typeof result.reading_timezone === "string" ? result.reading_timezone : "";
  // Chips keep the " · " separators as text so the summary still reads "회복 · 유연 · 시작".
  $("keywords").replaceChildren(...keywords.flatMap((word, i) => {
    const chip = document.createElement("span"); chip.className = "kw"; chip.textContent = word;
    if (!i) return [chip];
    const sep = document.createElement("span"); sep.className = "kw-sep"; sep.textContent = " · ";
    return [sep, chip];
  }));
  const dayGlyphs = pillarGlyphs(reading.day_pillar);
  if (dayGlyphs) {
    const label = document.createElement("span"); label.className = "day-pillar-label";
    label.textContent = `${{tomorrow:"내일의 일진", dday:"그날의 일진"}[view] || "오늘의 일진"} · ${dayGlyphs[0].ko}${dayGlyphs[1].ko}일`;
    $("day-pillar").replaceChildren(...dayGlyphs.map(tile), label);
  } else $("day-pillar").replaceChildren();
  drawDailySections(result);
  $("score").textContent = String(Math.round(reading.score));
  $("score").closest(".interpretation-index").style.setProperty("--score", String(Math.max(0, Math.min(100, Math.round(reading.score)))));
  $("daily-result").hidden = false;
  shareSource = {date:result.date, keywords, score:reading.score, view};
  measure("reading_viewed", view); showPremiumInterest();
}
function validDailySections(sections) {
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const text = value => typeof value === "string" && value.trim().length > 0;
  const guidance = value => object(value) && text(value.title) && text(value.text) && typeof value.qualifier === "string";
  if (!object(sections) || sections.schema_version !== 1
      || ![sections.theme, sections.action, sections.caution].every(guidance)
      || !Array.isArray(sections.evidence) || sections.evidence.length < 4 || sections.evidence.length > 5) return false;
  const allowed = new Set(["relation", "score", "cycle", "time", "limitations"]);
  const ids = new Set();
  for (const section of sections.evidence) {
    if (!object(section) || !allowed.has(section.id) || ids.has(section.id) || !text(section.title)
        || !Array.isArray(section.paragraphs) || !section.paragraphs.length || !section.paragraphs.every(text)) return false;
    ids.add(section.id);
  }
  return ["relation", "score", "cycle", "limitations"].every(id => ids.has(id));
}
function clearDailySections() {
  ["daily-theme-title", "day-relation", "daily-theme-qualifier", "daily-action-title", "daily-action",
   "daily-caution-title", "daily-caution", "daily-practice-qualifiers", "daily-evidence", "full-text"].forEach(id => $(id).replaceChildren());
  ["daily-guidance", "daily-theme-qualifier", "daily-practice-qualifiers", "daily-evidence"].forEach(id => $(id).hidden = true);
  $("full-text").hidden = false;
  $("daily-details").open = false;
  $("daily-details-summary").textContent = "계산 근거와 전체 풀이 읽기";
  delete $("daily-result").dataset.structured;
}
function drawDailySections(result) {
  clearDailySections();
  const sections = result.sections;
  if (!validDailySections(sections)) {
    $("full-text").textContent = typeof result.text === "string" ? result.text : "";
    return;
  }
  $("daily-theme-title").textContent = sections.theme.title;
  $("day-relation").textContent = sections.theme.text;
  $("daily-theme-qualifier").textContent = sections.theme.qualifier;
  $("daily-theme-qualifier").hidden = !sections.theme.qualifier;
  for (const name of ["action", "caution"]) {
    $("daily-" + name + "-title").textContent = sections[name].title;
    $("daily-" + name).textContent = sections[name].text;
  }
  // A shared qualifier plus a longer version with the same prefix needs only the longer original caption.
  const qualifiers = [...new Set([sections.action.qualifier, sections.caution.qualifier].filter(Boolean))];
  const captions = qualifiers.filter(value => !qualifiers.some(other => other !== value && other.startsWith(value + " · ")));
  $("daily-practice-qualifiers").replaceChildren(...captions.map(value => reportElement("p", "daily-qualifier", value)));
  $("daily-practice-qualifiers").hidden = !captions.length;
  $("daily-evidence").replaceChildren(...sections.evidence.map((section, index) => {
    const block = reportElement("section", "daily-evidence-section");
    const heading = reportElement("h4", "", section.title);
    heading.id = `daily-evidence-title-${index}`;
    block.setAttribute("aria-labelledby", heading.id);
    block.dataset.evidence = section.id;
    block.append(heading, ...section.paragraphs.map(value => reportElement("p", "", value)));
    return block;
  }));
  $("daily-guidance").hidden = false;
  $("daily-evidence").hidden = false;
  $("full-text").hidden = true;
  $("daily-details-summary").textContent = "해석 근거와 한계 읽기";
  $("daily-result").dataset.structured = "true";
}
let monthResizeObserver = null;
function clearResults() {
  clearShare(); clearIntegrated(); hidePremiumInterest();
  clearDailySections();
  monthResizeObserver?.disconnect(); monthResizeObserver = null;
  ["daily-result", "month-result", "chart-section", "compat-result"].forEach(id => $(id).hidden = true);
  ["pillars", "element-bars", "day-pillar", "chart-warning", "compat-text", "full-text", "month-text", "reading-timezone"].forEach(id => $(id).replaceChildren());
}
function reportElement(tag, className, text) {
  const node = document.createElement(tag); if (className) node.className = className;
  if (text !== undefined) node.textContent = text; return node;
}
function drawIntegrated(result) {
  const methods = new Set(["bazi", "ziwei", "western", "vedic"]);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const strings = value => Array.isArray(value) && value.every(item => typeof item === "string");
  const valid = object(result) && result.schema_version === 1 && result.scope === "natal" && result.kind === "integrated"
    && typeof result.text === "string" && !!result.text.trim() && result.text.length <= 100000 && typeof result.title === "string"
    && strings(result.summary) && strings(result.limitations)
    && Array.isArray(result.methods) && result.methods.length === 4
    && result.methods.every(x => object(x) && methods.has(x.method) && typeof x.label === "string" && typeof x.reason === "string"
      && typeof x.used_in_reading === "boolean" && ["ready", "partial", "unavailable"].includes(x.status))
    && new Set(result.methods.map(x => x.method)).size === 4
    && Array.isArray(result.evidence) && result.evidence.every(x => object(x) && typeof x.id === "string"
      && methods.has(x.method) && typeof x.label === "string" && typeof x.value === "string")
    && new Set(result.evidence.map(x => x.id)).size === result.evidence.length
    && Array.isArray(result.themes) && result.themes.every(theme => object(theme)
      && typeof theme.id === "string" && typeof theme.title === "string" && typeof theme.summary === "string"
      && Array.isArray(theme.claims) && theme.claims.every(claim => object(claim)
        && typeof claim.id === "string" && typeof claim.text === "string" && methods.has(claim.method)
        && typeof claim.rule_id === "string" && claim.time_scope === "natal" && strings(claim.evidence_ids))
      && ["agreements", "differences"].every(key => Array.isArray(theme[key]) && theme[key].every(item => object(item)
        && typeof item.text === "string" && strings(item.claim_ids) && strings(item.methods)
        && item.methods.every(method => methods.has(method)))));
  const factIds = new Set(valid ? result.evidence.map(x => x.id) : []);
  const linked = valid && result.themes.every(theme => {
    const claimIds = new Set(theme.claims.map(x => x.id));
    return claimIds.size === theme.claims.length
      && theme.claims.every(claim => claim.evidence_ids.length && claim.evidence_ids.every(id => factIds.has(id)))
      && [...theme.agreements, ...theme.differences].every(item => item.claim_ids.every(id => claimIds.has(id)));
  });
  if (!linked) {
    throw new Error("통합 리포트 형식을 확인하지 못했습니다. 오늘의 풀이는 다른 탭에서 볼 수 있습니다.");
  }
  $("integrated-title").textContent = result.title;
  const methodLabels = new Map(result.methods.map(method => [method.method, method.label]));
  $("integrated-methods").replaceChildren(...result.methods.map(method => {
    const box = reportElement("article", "integrated-method"); box.dataset.state = method.status;
    const state = method.used_in_reading ? (method.status === "ready" ? "풀이에 사용" : "일부 사용") : "풀이에서 제외";
    box.append(reportElement("h5", "", method.label), reportElement("span", "method-state", state), reportElement("p", "", method.reason || "계산한 범위의 근거만 사용합니다."));
    return box;
  }));
  $("integrated-summary").replaceChildren(...result.summary.map(text => reportElement("li", "", text)));
  const evidence = new Map(result.evidence.map(fact => [fact.id, fact]));
  $("integrated-themes").replaceChildren(...result.themes.map(theme => {
    const section = reportElement("section", "integrated-theme");
    section.append(reportElement("h4", "", theme.title));
    if (![...theme.agreements, ...theme.differences].some(item => item.text === theme.summary)) section.append(reportElement("p", "theme-summary", theme.summary));
    [["agreements", "함께 나타난 관점"], ["differences", "서로 다른 관점"]].forEach(([key, title]) => {
      const items = theme[key] || [];
      if (!items.length) return;
      const group = reportElement("div", `theme-${key}`); group.append(reportElement("h5", "", title));
      const list = reportElement("ul");
      items.forEach(item => list.append(reportElement("li", "", item.text)));
      group.append(list); section.append(group);
    });
    const details = reportElement("details", "theme-evidence"); details.append(reportElement("summary", "", "체계별 해석과 근거 보기"));
    const list = reportElement("ul", "theme-claims");
    (theme.claims || []).forEach(claim => {
      const item = reportElement("li");
      item.append(reportElement("span", "claim-method", methodLabels.get(claim.method) || claim.method), reportElement("p", "", claim.text));
      const refs = reportElement("ul", "claim-facts");
      (claim.evidence_ids || []).forEach(id => {
        const fact = evidence.get(id);
        if (fact) refs.append(reportElement("li", "", `${fact.label}: ${fact.value}`));
      });
      item.append(refs); list.append(item);
    });
    details.append(list); section.append(details); return section;
  }));
  $("integrated-evidence").replaceChildren(...result.evidence.flatMap(fact => [
    reportElement("dt", "", `${methodLabels.get(fact.method) || fact.method} · ${fact.label}`),
    reportElement("dd", "", fact.value),
  ]));
  $("integrated-limitations").replaceChildren(...result.limitations.map(text => reportElement("li", "", text)));
  $("integrated-text").textContent = result.text; integratedReport = result.text;
  $("integrated-result").hidden = false; measure("reading_viewed", "integrated"); showPremiumInterest();
}
function drawChart(result) {
  $("pillars").replaceChildren(); $("element-bars").replaceChildren();
  if (!result.ok) { $("chart-section").hidden = true; return; }
  const counts = {목:0, 화:0, 토:0, 금:0, 수:0};
  [["year", "년주"], ["month", "월주"], ["day", "일주"], ["time", "시주"]].forEach(([key, label]) => {
    const cell = document.createElement("div"); cell.className = "pillar";
    const title = document.createElement("span"); title.textContent = label;
    const value = document.createElement("strong");
    const glyphs = pillarGlyphs(result.pillars[key]);
    if (glyphs) { value.append(...glyphs.map(tile)); glyphs.forEach(g => counts[g.element]++); }
    else { value.className = "missing"; value.textContent = result.pillars[key] || "미산출"; }
    cell.append(title, value); $("pillars").append(cell);
  });
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total) {
    $("element-bars").replaceChildren(...Object.entries(counts).map(([element, n]) => {
      const row = document.createElement("div"); row.className = "bar";
      const name = document.createElement("span"); name.textContent = element;
      const track = document.createElement("span"); track.className = "track";
      const fill = document.createElement("span"); fill.className = `fill ${ELEMENT_CLASS[element]}`; fill.style.width = `${n / total * 100}%`;
      track.append(fill);
      const num = document.createElement("span"); num.className = "num"; num.textContent = String(n);
      row.append(name, track, num); return row;
    }));
  }
  $("chart-warning").textContent = result.warnings.join(" "); $("chart-section").hidden = false;
}
function drawMonth(data) {
  monthResizeObserver?.disconnect();
  const container = $("kline-chart");
  $("month-text").textContent = data.text; $("month-result").hidden = false;
  let previousWidth = 0;
  function render() {
    // Match SVG units to CSS pixels: shrinking the viewport must not shrink text.
    const chartWidth = Math.floor(container.getBoundingClientRect().width);
    if (chartWidth <= 48 || chartWidth === previousWidth) return;
    previousWidth = chartWidth;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${chartWidth} 270`); svg.setAttribute("role", "img");
    const title = document.createElementNS(ns, "title"); title.textContent = "이번 달 일별 해석 지수. 예측 확률이 아닙니다."; svg.append(title);
    const add = (tag, attributes, text) => { const el = document.createElementNS(ns, tag); Object.entries(attributes).forEach(([k,v]) => el.setAttribute(k, String(v))); if (text !== undefined) el.textContent = text; svg.append(el); return el; };
    const left = 36, right = chartWidth - 8, plotWidth = right - left;
    const y = value => 235 - value * 2;
    [0,25,50,75,100].forEach(value => { add("line", {x1:left,y1:y(value),x2:right,y2:y(value),stroke:"#ebe3d2"}); add("text", {x:3,y:y(value)+4,fill:"#6c6f7d","font-size":12},value); });
    const width = plotWidth / data.candles.length;
    const tickCount = Math.min(data.candles.length, Math.max(2, Math.floor(plotWidth / 60) + 1));
    const ticks = new Set(Array.from({length:tickCount}, (_, i) => Math.round(i * (data.candles.length - 1) / (tickCount - 1))));
    data.candles.forEach((c, i) => {
      const x = left + (i + .5) * width, color = c.close >= c.open ? "#c9503c" : "#2e4b7c";
      add("line", {x1:x,y1:y(c.high),x2:x,y2:y(c.low),stroke:color});
      const candle = add("rect", {x:x-width*.28,y:y(Math.max(c.open,c.close)),width:width*.56,height:Math.max(2,Math.abs(c.close-c.open)*2),fill:color,rx:1});
      const tip = document.createElementNS(ns,"title"); tip.textContent = `${c.date}: ${Math.round(c.close)} (해석 지수)`; candle.append(tip);
      if (ticks.has(i)) add("text", {x,y:257,"text-anchor":i === 0 ? "start" : i === data.candles.length-1 ? "end" : "middle",fill:"#69766d","font-size":12},c.date.slice(5));
    });
    container.replaceChildren(svg);
  }
  render();
  monthResizeObserver = new ResizeObserver(render);
  monthResizeObserver.observe(container);
}

async function loadView(view) {
  if (deleting || (view === "integrated" && !integratedEnabled)) return;
  const mine = cancelPending(); busy(true); showError("reading-error", "");
  $("empty-state").hidden = true; $("reading-panel").hidden = false; document.body.dataset.state = "reading";
  $("reading-title").textContent = profile.display_name ? `${profile.display_name}님의 하루` : "나의 하루";
  if (view === "integrated") $("reading-title").textContent = "여러 관점으로 읽는 나";
  clearResults();
  document.querySelectorAll("[data-view]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.view === view)));
  try {
    if (view === "integrated") {
      const result = await api("/api/readings/integrated");
      if (mine !== generation) return;
      if (!result || typeof result !== "object" || Array.isArray(result)) throw new Error("통합 리포트 형식을 확인하지 못했습니다. 오늘의 풀이는 다른 탭에서 볼 수 있습니다.");
      if (result.ok !== true || result.computed !== true) { showError("reading-error", typeof result.text === "string" ? result.text : "통합 풀이에 사용할 계산 근거가 없습니다."); return; }
      drawIntegrated(result); return;
    }
    const [result, chart] = await Promise.all([api(view === "month" ? "/api/kline" : `/api/readings/${view}`), api("/api/chart")]);
    if (mine !== generation) return;
    drawChart(chart);
    if (!result.ok || (view !== "month" && !result.computed)) { showError("reading-error", result.text); return; }
    if (view === "month") { drawMonth(result); measure("reading_viewed", view); showPremiumInterest(); return; }
    drawDaily(result, view);
  } catch (err) { if (err.name !== "AbortError" && mine === generation) showError("reading-error", err.message); }
  finally { if (mine === generation) busy(false); }
}
$("unknown-time").addEventListener("change", () => { $("birth-time").disabled = $("unknown-time").checked; if ($("unknown-time").checked) $("birth-time").value = ""; });
$("birth-form").addEventListener("input", () => {
  const day = new Intl.DateTimeFormat("en-CA", {timeZone:"Asia/Seoul", year:"numeric", month:"2-digit", day:"2-digit"}).format(new Date());
  if (csrf && formStartedDay !== day) { formStartedDay = day; measure("form_started", "entry"); }
});
$("birth-form").addEventListener("submit", async event => {
  event.preventDefault(); if (deleting || saving) return;
  const data = Object.fromEntries(new FormData(event.currentTarget)); data.birth_time = $("unknown-time").checked ? "" : $("birth-time").value;
  saving = true; syncSaveButton(); showError("form-error", "");
  let mine = null;
  try {
    if (birthLocationEnabled) {
      const latitude = $("birth-latitude").value, longitude = $("birth-longitude").value;
      if (Boolean(latitude) !== Boolean(longitude)) throw new Error("위도와 경도를 함께 입력하거나 두 항목을 모두 비워 주세요.");
      if (latitude && longitude) { data.latitude = Number(latitude); data.longitude = Number(longitude); }
      else { delete data.latitude; delete data.longitude; }
      if (!data.birthplace_text) delete data.birthplace_text;
    } else {
      delete data.birthplace_text; delete data.latitude; delete data.longitude;
    }
    if (!sessionReady) {
      try { await bootstrap(); }
      catch (_) { showError("form-error", "서비스에 연결하지 못했습니다. 잠시 후 저장을 다시 눌러 주세요."); return; }
    }
    if (deleting || !sessionReady) return;
    mine = cancelPending(); busy(true);
    const result = await api("/api/profile", {method:"PUT", body:JSON.stringify(data)});
    if (mine !== generation) return;
    profile = result.profile;
    setReadingWindow(result.reading_window);
    $("status").textContent = "출생정보를 저장했습니다.";
    await loadView("today"); $("reading-title").focus({preventScroll:true});
    if (window.matchMedia("(max-width: 620px)").matches) $("reading-panel").scrollIntoView({block:"start", behavior:"auto"});
  } catch (err) { if (err.name !== "AbortError" && (mine === null || mine === generation)) showError("form-error", err.message); }
  finally {
    if (mine === null || mine === generation) busy(false);
    saving = false; syncSaveButton();
  }
});
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => loadView(button.dataset.view)));
document.querySelectorAll("[data-premium-interest]").forEach(button => button.addEventListener("click", () => recordPremiumInterest(button)));
addEventListener("pagehide", () => { clearPremiumRequests(); clearPremiumMessages(); updatePremiumButtons(); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshPremiumDay(); });
$("delete-button").addEventListener("click", () => $("delete-dialog").showModal());
$("cancel-delete").addEventListener("click", () => $("delete-dialog").close());
$("delete-dialog").addEventListener("cancel", event => { if (deleting) event.preventDefault(); });
$("confirm-delete").addEventListener("click", async () => {
  if (deleting) return;
  deleting = true; cancelPending(); busy(true); $("confirm-delete").disabled = true;
  $("cancel-delete").disabled = true; $("delete-button").disabled = true;
  try {
    await api("/api/profile", {method:"DELETE"}); profile = null; formStartedDay = ""; empty(); $("birth-form").reset(); $("birth-time").disabled = true;
    $("delete-dialog").close(); await bootstrap(); $("status").textContent = "출생정보를 삭제했습니다.";
  } catch (err) {
    // The server may have committed deletion before delivery failed: hide stale data and resync.
    empty(); profile = null; formStartedDay = ""; $("birth-form").reset(); $("birth-time").disabled = true; $("delete-dialog").close();
    try {
      deleting = false; await bootstrap();
      if (profile) showError("form-error", "출생정보가 아직 남아 있습니다. 삭제를 다시 시도해 주세요.");
      else $("status").textContent = "출생정보가 삭제된 것을 확인했습니다.";
    } catch (_) { showError("form-error", "삭제 완료 여부를 확인하지 못했습니다. 새로고침 후 확인해 주세요."); }
  } finally { deleting = false; $("confirm-delete").disabled = false; $("cancel-delete").disabled = false; $("delete-button").disabled = false; busy(false); }
});
$("open-share").addEventListener("click", async () => {
  if (!shareSource || deleting) return;
  const source = shareSource, version = ++shareVersion;
  shareFile = null; $("share-canvas").hidden = true; $("download-share").disabled = true; $("native-share").hidden = true;
  $("share-placeholder").hidden = false; $("share-dialog").dataset.nativeShare = "false";
  $("share-status").textContent = "카드를 만들고 있습니다…";
  $("share-dialog").showModal(); measure("share_card_opened", source.view);
  try {
    const canvas = document.createElement("canvas");
    const blob = await FortuneShareCard.render(canvas, source);
    if (version !== shareVersion || !$("share-dialog").open) return;
    shareFile = new File([blob], `fortune-${source.date}.png`, {type:"image/png"});
    $("share-canvas").width = canvas.width; $("share-canvas").height = canvas.height;
    $("share-canvas").getContext("2d").drawImage(canvas, 0, 0);
    $("share-canvas").setAttribute("aria-label", `${source.date}. ${source.keywords.join(", ")}. 경험적 해석 지수 ${Math.round(source.score)}점. 예측 확률이 아닙니다.`);
    $("share-canvas").hidden = false; $("share-placeholder").hidden = true; $("download-share").disabled = false;
    const nativeShareAvailable = !!(navigator.share && navigator.canShare && navigator.canShare({files:[shareFile]}));
    $("native-share").hidden = !nativeShareAvailable;
    $("share-dialog").dataset.nativeShare = String(nativeShareAvailable);
    $("share-status").textContent = "미리보기를 확인한 뒤 나눠 보세요.";
  } catch (err) { if (version === shareVersion) $("share-status").textContent = err.message; }
});
$("close-share").addEventListener("click", () => $("share-dialog").close());
$("share-dialog").addEventListener("close", () => { ++shareVersion; shareFile = null; $("share-canvas").width = 0; });
$("download-share").addEventListener("click", () => {
  if (!shareFile || !shareSource) return;
  const url = URL.createObjectURL(shareFile), link = document.createElement("a");
  downloadUrls.add(url); link.href = url; link.download = shareFile.name; link.click();
  measure("share_download_requested", shareSource.view);
  $("share-status").textContent = "다운로드를 요청했습니다. 파일이 저장됐는지 확인해 주세요.";
  setTimeout(() => { URL.revokeObjectURL(url); downloadUrls.delete(url); }, 10000);
});
$("native-share").addEventListener("click", async () => {
  if (!shareFile || !shareSource) return;
  const version = shareVersion, view = shareSource.view;
  $("native-share").disabled = true; measure("share_requested", view);
  try {
    await navigator.share({files:[shareFile], title:"나의 하루를 읽는 세 단어"});
    if (version !== shareVersion) return;
    measure("share_handoff", view); $("share-status").textContent = "공유 화면에 전달했습니다. 실제 게시 여부는 선택한 앱에서 확인해 주세요.";
  } catch (err) {
    if (version !== shareVersion) return;
    measure(err.name === "AbortError" ? "share_cancelled" : "share_failed", view);
    $("share-status").textContent = err.name === "AbortError" ? "공유를 취소했습니다." : "이미지 공유를 열지 못했습니다. PNG를 다운로드해 주세요.";
  } finally { $("native-share").disabled = false; }
});
$("copy-share-link").addEventListener("click", async () => {
  const version = shareVersion, view = shareSource?.view;
  if (!view) return;
  const shareUrl = new URL("/", location.origin);
  shareUrl.searchParams.set("from", "card");
  const home = shareUrl.href;
  try {
    await navigator.clipboard.writeText(home);
    if (version !== shareVersion) return;
    measure("share_link_copied", view); $("share-status").textContent = "내 결과가 없는 홈 링크를 복사했습니다.";
  } catch (_) { if (version === shareVersion) $("share-status").textContent = `복사하지 못했습니다. 홈 주소: ${home}`; }
});
async function showIntegratedPage(version) {
  const selected = integratedPage, page = integratedPages[selected];
  if (!page) return;
  ["download-integrated-share", "integrated-page-prev", "integrated-page-next"].forEach(id => $(id).disabled = true);
  const bitmap = await createImageBitmap(page.blob);
  if (version !== integratedShareVersion || selected !== integratedPage || !$("integrated-share-dialog").open) { bitmap.close(); return; }
  const canvas = $("integrated-share-canvas"); canvas.width = 1080; canvas.height = 1350;
  canvas.getContext("2d").drawImage(bitmap, 0, 0); bitmap.close();
  canvas.hidden = false; canvas.setAttribute("aria-label", `통합 성향 리포트 ${selected + 1}/${integratedPages.length} 페이지. ${page.text}`);
  $("integrated-share-placeholder").hidden = true;
  $("integrated-page-number").textContent = `${selected + 1} / ${integratedPages.length}`;
  $("integrated-share-status").textContent = `원문을 그대로 ${integratedPages.length}장에 나눴습니다.`;
  $("download-integrated-share").disabled = false;
  $("integrated-page-prev").disabled = selected === 0;
  $("integrated-page-next").disabled = selected + 1 === integratedPages.length;
}
function integratedImageError(error, version) {
  if (error.name === "AbortError" || version !== integratedShareVersion) return;
  integratedPages = [];
  $("integrated-share-canvas").width = 0; $("integrated-share-canvas").hidden = true;
  $("integrated-share-placeholder").hidden = true;
  ["download-integrated-share", "integrated-page-prev", "integrated-page-next"].forEach(id => $(id).disabled = true);
  $("integrated-page-number").textContent = "";
  $("integrated-share-status").textContent = "이미지를 만들지 못했습니다. 닫은 뒤 다시 시도해 주세요. 결과 원문은 화면에서 계속 읽을 수 있습니다.";
}
$("open-integrated-share").addEventListener("click", async () => {
  if (!integratedEnabled || !integratedReport || deleting) return;
  clearIntegrated(false);
  const version = integratedShareVersion, text = integratedReport;
  $("integrated-share-status").textContent = "결과 원문을 이미지로 만들고 있습니다…";
  $("integrated-share-dialog").showModal();
  try {
    const pages = await FortuneIntegratedCard.render(text, () => version === integratedShareVersion && $("integrated-share-dialog").open);
    if (version !== integratedShareVersion || !$("integrated-share-dialog").open) return;
    integratedPages = pages; await showIntegratedPage(version);
  } catch (error) { integratedImageError(error, version); }
});
$("close-integrated-share").addEventListener("click", () => clearIntegrated(false));
$("integrated-share-dialog").addEventListener("cancel", event => { event.preventDefault(); clearIntegrated(false); });
[["integrated-page-prev", -1], ["integrated-page-next", 1]].forEach(([id, direction]) => $(id).addEventListener("click", () => {
  const target = integratedPage + direction;
  if (target < 0 || target >= integratedPages.length) return;
  integratedPage = target; const version = integratedShareVersion;
  showIntegratedPage(version).catch(error => integratedImageError(error, version));
}));
$("download-integrated-share").addEventListener("click", () => {
  const page = integratedPages[integratedPage];
  if (!page || deleting || !$("integrated-share-dialog").open) return;
  const url = URL.createObjectURL(page.blob); integratedUrls.add(url);
  const link = document.createElement("a"); link.href = url; link.download = `fortune-portrait-${String(integratedPage + 1).padStart(2, "0")}.png`;
  link.click();
  setTimeout(() => { URL.revokeObjectURL(url); integratedUrls.delete(url); }, 60000);
});
async function loadSpecial(view, payload) {
  if (deleting || !profile) return;
  const mine = cancelPending(); busy(true); clearResults(); showError("reading-error", "");
  if (view === "dday") pendingDatedGeneration = mine;
  document.querySelectorAll("[data-view]").forEach(b => b.setAttribute("aria-pressed", "false"));
  try {
    const result = await api(view === "dday" ? "/api/readings/date" : "/api/compat", {method:"POST", body:JSON.stringify(payload)});
    if (mine !== generation) return;
    if (!result.ok || !result.computed) { showError("reading-error", result.text); return; }
    if (view === "dday") {
      drawDaily(result, view); $("daily-result").scrollIntoView({block:"start", behavior:"auto"});
    } else {
      $("compat-text").textContent = result.text; $("compat-result").hidden = false;
      $("compat-title").focus({preventScroll:true}); $("compat-result").scrollIntoView({block:"start", behavior:"auto"});
      measure("reading_viewed", "compat"); showPremiumInterest();
    }
  } catch (err) {
    if (err.name !== "AbortError" && mine === generation) { showError("reading-error", err.message); $("reading-error").scrollIntoView({block:"center"}); }
  } finally { if (mine === generation) { pendingDatedGeneration = null; busy(false); } }
}
$("date-form").addEventListener("input", () => {
  if (deleting || (pendingDatedGeneration !== generation && shareSource?.view !== "dday")) return;
  // A changed date or situation invalidates only its dated result, including a late reply.
  cancelPending(); busy(false); clearResults(); showError("reading-error", "");
});
$("date-form").addEventListener("submit", event => {
  event.preventDefault(); loadSpecial("dday", Object.fromEntries(new FormData(event.currentTarget)));
});
$("partner-unknown-time").addEventListener("change", () => {
  $("partner-time").disabled = $("partner-unknown-time").checked;
  if ($("partner-unknown-time").checked) $("partner-time").value = "";
});
$("compat-form").addEventListener("submit", event => {
  event.preventDefault(); if (deleting) return;
  const partner = Object.fromEntries(new FormData(event.currentTarget));
  partner.birth_time = $("partner-unknown-time").checked ? "" : $("partner-time").value;
  loadSpecial("compat", {partner});
  event.currentTarget.reset(); $("partner-time").disabled = true;
});
const today = new Date(); $("birth-date").max = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,"0")}-${String(today.getDate()).padStart(2,"0")}`;
$("partner-date").max = $("birth-date").max;
bootstrap().catch(err => showError("form-error", err.name === "TimeoutError"
  ? err.message : "서비스에 연결하지 못했습니다. 잠시 후 저장을 다시 눌러 주세요."));
// Typography rule: text that wraps to two or more lines gets 150% leading; single-line text keeps auto.
// CSS cannot see line counts, so measure each text block at auto leading and tag the wrapped ones.
const LEADING_SELECTOR = "p, li, h1, h2, h3, label, legend, summary, figcaption, button, .preserve-lines, .kw";
let leadingFrame = 0;
function lineCount(el) {
  const range = document.createRange(); range.selectNodeContents(el);
  // Boxes that overlap vertically share a line (chips, separators and inline emphasis sit at different tops).
  let lines = 0, bottom = -Infinity;
  [...range.getClientRects()].filter(r => r.height).sort((a, b) => a.top - b.top).forEach(r => {
    if (r.top >= bottom - 1) { lines++; bottom = r.bottom; } else bottom = Math.max(bottom, r.bottom);
  });
  return lines;
}
function applyLeading() {
  leadingFrame = 0;
  const blocks = [...document.querySelectorAll(LEADING_SELECTOR)].filter(el => el.offsetParent || el.getClientRects().length);
  blocks.forEach(el => el.classList.remove("lh-multi"));          // measure everything at auto leading first
  const wrapped = blocks.filter(el => lineCount(el) >= 2);
  wrapped.forEach(el => el.classList.add("lh-multi"));            // leading never changes where lines break
}
function scheduleLeading() { if (!leadingFrame) leadingFrame = requestAnimationFrame(applyLeading); }
new MutationObserver(scheduleLeading).observe(document.body, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:["hidden", "open"]});
addEventListener("resize", scheduleLeading);
document.fonts.ready.then(scheduleLeading);
scheduleLeading();
