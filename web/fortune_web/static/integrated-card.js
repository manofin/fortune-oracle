"use strict";
// Paginate the already displayed report. This module never receives a birth profile.
window.FortuneIntegratedCard = Object.freeze({
  async render(text, isCurrent = () => true) {
    if (typeof text !== "string" || !text.trim() || text.length > 100000) {
      throw new Error("이미지로 만들 결과 원문을 확인하지 못했습니다.");
    }
    const check = () => { if (!isCurrent()) throw new DOMException("취소됨", "AbortError"); };
    await Promise.all([document.fonts.load("38px Pretendard", text), document.fonts.load("38px FortuneKorean", text)]);
    check();
    const canvas = document.createElement("canvas"); canvas.width = 1080; canvas.height = 1350;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("이 브라우저에서 이미지를 만들 수 없습니다.");
    ctx.font = "38px Pretendard, FortuneKorean, sans-serif";
    if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
    // Every character belongs to exactly one line's source, including literal newlines.
    // Wrapping never trims, substitutes, summarizes or drops characters.
    const rows = [];
    const segmenter = typeof Intl.Segmenter === "function" ? new Intl.Segmenter("ko", {granularity:"grapheme"}) : null;
    const characters = segmenter ? [...segmenter.segment(text)].map(x => x.segment) : Array.from(text);
    let line = "";
    for (const char of characters) {
      if (char === "\n" || char === "\r\n" || char === "\r") { rows.push({text:line, source:line + char}); line = ""; continue; }
      if (line && ctx.measureText(line + char).width > 920) {
        const space = line.lastIndexOf(" ");
        if (space > line.length * .5) {
          // Keep words together when possible; the trailing space stays in source.
          const prefix = line.slice(0, space + 1); rows.push({text:prefix, source:prefix}); line = line.slice(space + 1);
        } else if (/^[.,!?，。！？、：；:;）)\]」』】》〉”’％%]/u.test(char)) {
          const previous = segmenter ? [...segmenter.segment(line)].map(x => x.segment) : Array.from(line);
          const tail = previous.pop(); const prefix = previous.join("");
          rows.push({text:prefix, source:prefix}); line = tail;
        } else { rows.push({text:line, source:line}); line = ""; }
      }
      if (ctx.measureText(char).width > 920) throw new Error("표시할 문자를 이미지에 배치하지 못했습니다.");
      line += char;
    }
    if (line) rows.push({text:line, source:line});
    if (rows.map(row => row.source).join("") !== text) throw new Error("원문과 이미지 내용을 대조하지 못했습니다.");
    const perPage = 18, contents = [];
    for (let offset = 0; offset < rows.length;) {
      let end = Math.min(offset + perPage, rows.length);
      // Keep a short section heading with the following text rather than orphaning it.
      if (end < rows.length && end - offset > 2 && rows[end - 2].text === ""
          && rows[end - 1].text.trim() && Array.from(rows[end - 1].text).length <= 16 && rows[end].text.trim()) end--;
      contents.push(rows.slice(offset, end)); offset = end;
    }
    const pageCount = contents.length, pages = [];
    if (pageCount > 100) throw new Error("결과가 너무 길어 이미지로 만들 수 없습니다. 화면의 원문을 확인해 주세요.");
    for (let page = 0; page < pageCount; page++) {
      check();
      ctx.fillStyle = "#fbf7ef"; ctx.fillRect(0, 0, 1080, 1350);
      ctx.fillStyle = "#151a2e"; ctx.fillRect(0, 0, 1080, 156);
      ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
      ctx.font = "26px Pretendard, FortuneKorean, sans-serif"; ctx.fillStyle = "#e8bd62";
      ctx.fillText("FORTUNE ORACLE", 80, 58);
      ctx.font = "44px Pretendard, FortuneKorean, sans-serif"; ctx.fillStyle = "#fffdf8";
      ctx.fillText("여러 관점으로 읽는 나", 80, 120);
      ctx.fillStyle = "#1e2233"; ctx.font = "38px Pretendard, FortuneKorean, sans-serif";
      const content = contents[page];
      content.forEach((row, index) => ctx.fillText(row.text, 80, 228 + index * 54));
      ctx.strokeStyle = "#e9e1d0"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(80, 1230); ctx.lineTo(1000, 1230); ctx.stroke();
      ctx.font = "26px Pretendard, FortuneKorean, sans-serif"; ctx.fillStyle = "#5d6170";
      ctx.fillText("출생 성향 리포트 · 결과 원문", 80, 1288);
      ctx.textAlign = "right"; ctx.fillText(`${page + 1} / ${pageCount}`, 1000, 1288);
      const blob = await new Promise((resolve, reject) => canvas.toBlob(value => value ? resolve(value)
        : reject(new Error("이미지를 만들지 못했습니다. 다시 시도해 주세요.")), "image/png"));
      check();
      pages.push({blob, text:content.map(row => row.source).join("")});
    }
    canvas.width = 0; canvas.height = 0;
    return pages;
  },
});
