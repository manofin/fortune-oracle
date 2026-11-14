"""Build the common OG banner from static text and the checked-in font, offline.

Uses the persistent dev-venv and PLAYWRIGHT_BROWSERS_PATH; no profile or service DB.
This is a build-time tool, never run in response to a crawler request.
"""
import base64
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    static = Path(__file__).resolve().parents[1] / "web/fortune_web/static"
    font = base64.b64encode((static / "fonts/pretendard-variable.woff2").read_bytes()).decode()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        png = page.evaluate("""async font => {
          const face = new FontFace('Banner', `url(data:font/woff2;base64,${font})`, {weight:'45 930'});
          document.fonts.add(await face.load());
          const canvas = document.createElement('canvas'); canvas.width=1200; canvas.height=630;
          const c = canvas.getContext('2d');
          c.fillStyle='#fbf7ef'; c.fillRect(0,0,1200,630);
          c.fillStyle='#151a2e'; c.fillRect(0,0,1200,476);
          const text=(s,x,y,size,color,weight=500)=>{
            c.font=`${weight} ${size}px Banner`; c.fillStyle=color;
            c.letterSpacing=`${-.03*size}px`; c.fillText(s,x,y);
          };
          ['#3f9a6c','#d6513c','#b4841f','#7d8794','#2e4b7c'].forEach((color,i)=>{
            c.strokeStyle=color; c.lineWidth=8; c.beginPath();
            c.arc(84,76,17,-Math.PI/2+i*2*Math.PI/5,-Math.PI/2+(i+1)*2*Math.PI/5); c.stroke();
          });
          text('FORTUNE ORACLE',120,86,26,'#fbf7ef',700);
          text('오늘의 나에게,',64,218,76,'#fbf7ef',700);
          text('작은 힌트 하나.',64,318,76,'#e8bd62',700);
          text('내 사주로 오늘의 세 단어를 읽어보세요.',68,398,30,'#dedfE8');
          text('계산 근거와 해석을 구분합니다.',64,544,30,'#1e2233',600);
          text('오락과 자기성찰을 위한 참고 · 개인 결과가 아닌 서비스 소개',64,588,22,'#5d6170');
          return canvas.toDataURL('image/png').split(',')[1];
        }""", font)
        browser.close()
    target = static / "share/fortune-oracle-og.png"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(base64.b64decode(png))
    print(f"Built {target.name}: 1200×630, {target.stat().st_size} bytes; common copy only")


if __name__ == "__main__":
    main()
