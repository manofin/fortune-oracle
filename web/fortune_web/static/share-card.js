"use strict";
// This renderer accepts a small projection, never a profile, natal chart or reading text.
window.FortuneShareCard = Object.freeze({
  async render(canvas, {date, keywords, score}) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(score) || score < 0 || score > 100
        || !Array.isArray(keywords) || keywords.length !== 3
        || keywords.some(word => typeof word !== "string" || word.length > 20 || !word.trim())) {
      throw new Error("공유할 계산 결과를 확인하지 못했습니다.");
    }
    await Promise.all([document.fonts.load("40px Pretendard", "하루의키워드"), document.fonts.load("40px FortuneKorean", "하루의키워드")]);
    canvas.width = 1080; canvas.height = 1350;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("이 브라우저에서 이미지 카드를 만들 수 없습니다.");
    const colors = {paper:"#fbf7ef", ink:"#1e2233", muted:"#5d6170", light:"#fbf6ea", sage:"#e8bd62", line:"#3a4370", panel:"#1b2240", rule:"#e6dcc8"};
    ctx.fillStyle = colors.paper; ctx.fillRect(0, 0, 1080, 1350);
    // Same -3% tracking as the page where the canvas supports it.
    const setTracking = size => { if ("letterSpacing" in ctx) ctx.letterSpacing = `${(-0.03 * size).toFixed(2)}px`; };
    const text = (value, x, y, size, color = colors.ink, align = "left") => {
      ctx.fillStyle = color; ctx.font = `${size}px Pretendard, FortuneKorean, sans-serif`; setTracking(size);
      ctx.textAlign = align; ctx.fillText(value, x, y);
    };
    const line = (x1, y, x2, color) => {
      ctx.strokeStyle = color; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke();
    };
    // One shared alignment for identity/date, the keyword group and supporting facts.
    // Brand mark: a ring of the five element colours, matching the web header.
    ["#3f9a6c", "#d6513c", "#b4841f", "#7d8794", "#2e4b7c"].forEach((color, i) => {
      ctx.strokeStyle = color; ctx.lineWidth = 9; ctx.beginPath();
      ctx.arc(89, 85, 15, -Math.PI / 2 + i * 2 * Math.PI / 5, -Math.PI / 2 + (i + 1) * 2 * Math.PI / 5); ctx.stroke();
    });
    text("FORTUNE ORACLE", 126, 94, 26);
    text(date.replaceAll("-", "."), 1008, 94, 28, colors.muted, "right");
    line(72, 132, 1008, colors.rule);
    text("나의 하루를 읽는", 72, 233, 64);
    text("세 단어.", 72, 313, 64);

    // Common region + similarity: the three words have equal weight, spacing and color.
    ctx.fillStyle = colors.panel; ctx.beginPath(); ctx.roundRect(64, 366, 952, 648, 32); ctx.fill();
    let wordSize = 124;
    ctx.font = `${wordSize}px Pretendard, FortuneKorean`; setTracking(wordSize);
    while (keywords.some(word => ctx.measureText(word).width > 750) && wordSize > 32) {
      ctx.font = `${--wordSize}px Pretendard, FortuneKorean`; setTracking(wordSize);
    }
    const metrics = ctx.measureText(keywords.join(""));
    const wordOffset = (metrics.actualBoundingBoxAscent - metrics.actualBoundingBoxDescent) / 2;
    keywords.forEach((word, index) => {
      const center = 474 + index * 216;
      text(String(index + 1).padStart(2, "0"), 112, center + 11, 28, colors.sage);
      text(word, 188, center + wordOffset, wordSize, colors.light);
      if (index < 2) line(112, 582 + index * 216, 968, colors.line);
    });

    // Keep the index and its limitation adjacent, subordinate to the words.
    text("경험적 해석 지수", 72, 1090, 30);
    text("예측 확률이 아닙니다.", 72, 1141, 28, colors.muted);
    text(String(Math.round(score)), 920, 1138, 76, colors.ink, "right");
    text("/ 100", 1008, 1138, 28, colors.muted, "right");
    line(72, 1198, 1008, colors.rule);
    text("내 하루에 비춰 보고, 선택은 내 방식으로.", 72, 1263, 30);
    text("사주·일진 기반 해석 · 오락과 자기성찰을 위한 참고", 72, 1310, 24, colors.muted);
    return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob)
      : reject(new Error("이미지를 만들지 못했습니다. 다시 시도해 주세요.")), "image/png"));
  },
});
