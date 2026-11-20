"use strict";
(() => {
  const PRODUCTS = ["self_manual_v1", "conversation_guide_v1", "four_perspectives_v1"];
  const TIMEOUT_MS = 8000;
  const dayKey = () => new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit"
  }).format(new Date());

  function init() {
    const products = PRODUCTS.map(id => ({
      id,
      open: document.querySelector(`[data-sample-open="${id}"]`),
      interest: document.querySelector(`[data-sample-interest="${id}"]`),
      adult: document.querySelector(`[data-sample-adult="${id}"]`),
      status: document.querySelector(`[data-sample-status="${id}"]`),
      report: document.getElementById(`sp-report-${id}`),
      close: document.querySelector(`[data-sample-close="${id}"]`),
      title: document.getElementById(`sp-title-${id}`)?.textContent || "리포트",
      viewed: false, confirmed: false, request: null, retry: false, nativeToggle: false
    })).filter(p => p.open && p.interest && p.adult && p.status && p.report);
    const deleteButton = document.getElementById("sp-delete-button");
    const dialog = document.getElementById("sp-delete-dialog");
    const confirm = document.getElementById("sp-delete-confirm");
    const cancel = document.getElementById("sp-delete-cancel");
    const deleteStatus = document.getElementById("sp-delete-status");
    let csrf = "", generation = 0, day = dayKey(), deleting = false, deletionComplete = false;
    // A session GET may set a cookie. Always drain it before replacing a session
    // or deleting one; merely ignoring its JSON would not prevent a cookie race.
    let sessionFlight = null, browserStateChannel = null;

    function connectBrowserState() {
      if (browserStateChannel || !window.BroadcastChannel) return;
      try {
        browserStateChannel = new BroadcastChannel("fortune-browser-state");
        browserStateChannel.onmessage = event => {
          if (event.data === "profile-invalidated") {
            invalidate("다른 탭에서 정보가 바뀌었어요. 샘플 다시 읽기로 이용 기록을 확인해 주세요.");
          }
        };
      } catch (_) { /* Restored pages also invalidate below when channels are blocked. */ }
    }
    function notifyBrowserState() {
      // A fixed, transient signal carries no identity, personal data or URL.
      try { browserStateChannel?.postMessage("profile-invalidated"); } catch (_) { /* optional coordination */ }
    }

    const isOpen = p => p.report.tagName === "DETAILS" ? p.report.open : !p.report.hidden;
    function setOpen(p, value) {
      if (p.report.tagName === "DETAILS") p.report.open = value;
      else p.report.hidden = !value;
      p.open.setAttribute("aria-expanded", String(value));
    }
    function message(p, text) { p.status.textContent = text; }
    function render() {
      products.forEach(p => {
        const busy = Boolean(p.request);
        p.open.disabled = deleting || busy;
        p.open.setAttribute("aria-controls", p.report.id);
        p.open.setAttribute("aria-expanded", String(isOpen(p)));
        p.open.setAttribute("aria-busy", String(busy && p.request.kind === "view"));
        p.open.textContent = busy && p.request.kind === "view" ? "샘플 확인 중…"
          : p.retry ? "샘플 다시 읽기" : isOpen(p) && p.viewed ? "샘플 닫기" : "샘플 읽기";
        p.open.setAttribute("aria-label", `${p.title} · ${p.open.textContent}`);
        p.adult.disabled = deleting || busy;
        p.interest.disabled = deleting || busy || !isOpen(p) || !p.viewed || !p.adult.checked || p.confirmed;
        p.interest.setAttribute("aria-busy", String(busy && p.request.kind === "interest"));
        p.interest.dataset.confirmed = String(p.confirmed);
        p.interest.textContent = busy && p.request.kind === "interest" ? "관심 기록 중…"
          : p.confirmed ? "관심을 기록했어요" : "이 가격이면 관심 있어요";
        p.interest.setAttribute("aria-label", `${p.title} · ${p.interest.textContent}`);
      });
      if (deleteButton) deleteButton.disabled = deleting;
      if (confirm) { confirm.disabled = deleting || deletionComplete; confirm.textContent = deleting ? "삭제 확인 중…" : "삭제하기"; }
      if (cancel) cancel.disabled = deleting;
      if (dialog) dialog.setAttribute("aria-busy", String(deleting));
    }
    function invalidate(text, forgetSession = true) {
      ++generation;
      if (forgetSession) csrf = "";
      products.forEach(p => {
        p.request?.controller.abort();
        p.request = null;
        p.nativeToggle = false;
        p.viewed = false; p.confirmed = false; p.adult.checked = false;
        p.retry = isOpen(p);
        message(p, text);
      });
      render();
    }
    function refreshDay() {
      const next = dayKey();
      if (next === day) return false;
      day = next;
      invalidate("한국 날짜가 바뀌었어요. 샘플을 다시 읽고 관심을 표시해 주세요.", false);
      return true;
    }

    // The deadline covers headers AND JSON consumption. No server text, profile,
    // identifiers, or arbitrary response fields are rendered or persisted.
    async function requestJSON(path, options = {}, parentSignal = null) {
      const controller = new AbortController();
      let timer;
      let onAbort;
      const cancelled = new Promise((_, reject) => {
        onAbort = () => { controller.abort(); reject(new Error("cancelled")); };
        if (parentSignal?.aborted) onAbort();
        else parentSignal?.addEventListener("abort", onAbort, {once: true});
        timer = setTimeout(() => { controller.abort(); reject(new Error("timeout")); }, TIMEOUT_MS);
      });
      const operation = (async () => {
        const response = await fetch(path, {credentials: "same-origin", cache: "no-store",
          ...options, signal: controller.signal});
        // Revocation must invalidate the UI even if the error body is malformed.
        if (response.status === 401 || response.status === 403) return {status: response.status, data: null};
        let data = null;
        try { data = await response.json(); } catch (_) { /* unconfirmed acknowledgement */ }
        return {status: response.status, data};
      })();
      try { return await Promise.race([operation, cancelled]); }
      finally {
        clearTimeout(timer);
        parentSignal?.removeEventListener("abort", onAbort);
      }
    }
    function startSession() {
      const flight = {generation, promise: null};
      flight.promise = (async () => {
        const {status, data} = await requestJSON("/api/session");
        if (status !== 200 || data?.ok !== true || typeof data.csrf !== "string" || !/^[a-f0-9]{64}$/.test(data.csrf)) {
          throw new Error("session_unconfirmed");
        }
        return data.csrf;
      })();
      sessionFlight = flight;
      // Attach both handlers so failed, abandoned flights cannot reject unhandled.
      flight.promise.then(() => { if (sessionFlight === flight) sessionFlight = null; },
        () => { if (sessionFlight === flight) sessionFlight = null; });
      return flight;
    }
    async function ensureSession(mine) {
      if (csrf) return csrf;
      let flight = sessionFlight || startSession();
      let token = await flight.promise;
      if (mine !== generation || deleting) throw new Error("stale");
      // A pre-invalidation GET must settle before a fresh explicit open can GET.
      if (flight.generation !== mine) {
        flight = sessionFlight || startSession();
        token = await flight.promise;
      }
      if (mine !== generation || deleting) throw new Error("stale");
      csrf = token;
      return token;
    }
    async function record(p, kind) {
      if (deleting || p.request) return;
      refreshDay();
      if (kind === "interest" && (!p.viewed || !isOpen(p) || !p.adult.checked || p.confirmed)) return;
      const mine = generation, requestDay = day;
      const request = {kind, controller: new AbortController()};
      p.request = request;
      p.retry = false;
      message(p, kind === "view" ? "샘플을 열었어요. 조회 기록을 확인하고 있어요…" : "관심을 기록하고 있어요…");
      render();
      const current = () => generation === mine && !deleting && p.request === request;
      try {
        const token = await ensureSession(mine);
        if (!current()) return;
        const {status, data} = await requestJSON("/api/events", {
          method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": token},
          body: JSON.stringify({event: kind === "view" ? "product_sample_viewed" : "product_sample_interest", view: p.id})
        }, request.controller.signal);
        if (!current()) return;
        if (status === 401 || status === 403) {
          invalidate("이용 세션을 다시 확인해야 해요. 샘플 다시 읽기를 눌러 주세요.");
          return;
        }
        if (requestDay !== dayKey()) { refreshDay(); return; }
        if (status === 409 && data?.error === "sample_not_viewed") {
          p.viewed = false; p.confirmed = false; p.retry = true;
          message(p, "조회 기록을 다시 확인해야 해요. 샘플 다시 읽기를 눌러 주세요.");
          return;
        }
        if (status !== 202 || data?.ok !== true) throw new Error("unconfirmed");
        if (kind === "view") {
          p.viewed = true;
          message(p, "샘플 조회를 기록했어요. 성인 확인 후 이 가격에 관심을 표시할 수 있어요.");
        } else {
          p.confirmed = true;
          message(p, "관심을 기록했어요. 결제나 알림 신청은 진행되지 않아요.");
        }
      } catch (_) {
        if (!current()) return;
        if (kind === "view") {
          p.viewed = false; p.retry = true;
          message(p, "조회 기록을 확인하지 못했어요. 본문은 읽을 수 있어요. 샘플 다시 읽기로 재시도해 주세요.");
        } else {
          message(p, "관심이 기록됐는지 확인하지 못했어요. 잠시 후 다시 눌러 주세요.");
        }
      } finally {
        if (p.request === request) { p.request = null; render(); }
      }
    }

    products.forEach(p => {
      p.status.setAttribute("role", "status");
      p.status.setAttribute("aria-live", "polite");
      p.open.addEventListener("click", () => {
        if (deleting || p.request) return;
        refreshDay();
        if (isOpen(p) && p.viewed && !p.retry) { setOpen(p, false); render(); return; }
        setOpen(p, true);
        // Expanding a desktop card can move the whole report below the fold.
        // Move focus before the opener becomes disabled during acknowledgement.
        const summary = p.report.querySelector("summary");
        if (summary) {
          summary.focus({preventScroll: true});
          summary.scrollIntoView({block: "start", behavior: "auto"});
        }
        if (p.viewed) { render(); return; }
        void record(p, "view");
      });
      if (p.close) {
        p.close.hidden = false;
        p.close.addEventListener("click", () => {
          setOpen(p, false);
          render();
          // An acknowledgement may still be pending; the native summary remains
          // usable in that case and avoids focusing a disabled opener.
          const target = p.open.disabled ? p.report.querySelector("summary") : p.open;
          target?.focus({preventScroll: true});
          target?.scrollIntoView({block: "nearest", behavior: "auto"});
        });
      }
      p.interest.addEventListener("click", () => { void record(p, "interest"); });
      p.adult.addEventListener("change", () => { refreshDay(); render(); });
      // Native summary keyboard/click activation also counts as an explicit open.
      // Gate on the activation, since initial markup and bfcache can dispatch
      // toggle events too, and neither should silently bootstrap a session.
      p.report.addEventListener("click", event => {
        const summary = event.target.closest?.("summary");
        if (!summary || summary.parentElement !== p.report) return;
        if (deleting) { event.preventDefault(); return; }
        p.nativeToggle = true;
      });
      p.report.addEventListener("toggle", () => {
        const activated = p.nativeToggle;
        p.nativeToggle = false;
        if (activated && isOpen(p) && !deleting && !p.request) {
          refreshDay();
          if (!p.viewed) void record(p, "view");
        }
        render();
      });
    });

    if (deleteButton && dialog && confirm && cancel && deleteStatus) {
      deleteStatus.setAttribute("role", "status");
      deleteStatus.setAttribute("aria-live", "polite");
      deleteButton.addEventListener("click", () => {
        if (deleting) return;
        deletionComplete = false;
        deleteStatus.textContent = "이 브라우저의 출생정보와 이용 기록을 삭제합니다. 익명 일별 집계는 남습니다.";
        render();
        if (!dialog.open) dialog.showModal();
      });
      cancel.addEventListener("click", event => {
        event.preventDefault();
        if (!deleting) dialog.close();
      });
      dialog.addEventListener("cancel", event => { if (deleting) event.preventDefault(); });
      confirm.addEventListener("click", async event => {
        event.preventDefault();
        if (deleting || deletionComplete) return;
        const knownToken = csrf, existingFlight = sessionFlight;
        deleting = true;
        notifyBrowserState();
        invalidate("삭제를 확인하고 있어요…");
        const mine = generation;
        deleteStatus.textContent = "삭제를 확인하고 있어요. 완료될 때까지 기다려 주세요.";
        render();
        try {
          let token = knownToken;
          if (existingFlight) {
            // Do not abort a GET then race it with DELETE: its Set-Cookie could
            // arrive after deletion. Drain it and use its token for this DELETE.
            try { token = await existingFlight.promise; } catch (_) { token = ""; }
          }
          if (mine !== generation) throw new Error("stale");
          if (!token) token = await (sessionFlight || startSession()).promise;
          if (mine !== generation) throw new Error("stale");
          const {status, data} = await requestJSON("/api/profile", {
            method: "DELETE", headers: {"X-CSRF-Token": token}
          });
          notifyBrowserState();
          if (mine !== generation) throw new Error("stale");
          if (status !== 401 && (status !== 200 || data?.ok !== true)) throw new Error("delete_unconfirmed");
          invalidate("이 브라우저의 정보를 삭제했어요. 샘플은 계속 읽을 수 있어요.");
          deletionComplete = true;
          deleteStatus.textContent = "이 브라우저의 출생정보와 이용 기록을 삭제했어요. 익명 일별 집계는 남습니다.";
        } catch (_) {
          notifyBrowserState();
          invalidate("삭제 완료를 확인하지 못했어요. 삭제 창에서 다시 시도해 주세요.");
          deleteStatus.textContent = "삭제 완료를 확인하지 못했어요. 연결을 확인하고 삭제하기를 다시 눌러 주세요.";
        } finally {
          deleting = false;
          render();
        }
      });
    }
    window.addEventListener("pagehide", () => {
      invalidate("화면을 나갔어요. 돌아온 뒤 샘플 다시 읽기를 눌러 주세요.");
      browserStateChannel?.close(); browserStateChannel = null;
    });
    window.addEventListener("pageshow", event => {
      connectBrowserState();
      if (event.persisted) {
        day = dayKey();
        invalidate("화면으로 돌아왔어요. 샘플 다시 읽기를 눌러 이용 기록을 다시 확인해 주세요.");
      }
    });
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshDay(); });
    window.addEventListener("focus", refreshDay);
    // No API request, cookie access, or storage access on page load.
    connectBrowserState();
    render();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, {once: true});
  else init();
})();
