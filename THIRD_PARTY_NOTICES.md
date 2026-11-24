# 제3자 자료 고지

이 파일은 포함한 자료의 출처와 고지 위치를 정리합니다. 프로젝트 전체에 새로운 라이선스를 부여하거나 개별 의존성의 조건을 대체하지 않습니다.

| 자료 | 출처 | 포함된 고지 |
| --- | --- | --- |
| `bazi_reference.py`가 참조한 bazi-skill 자료 | [jinchenma94/bazi-skill](https://github.com/jinchenma94/bazi-skill) | [MIT 고지](licenses/bazi-skill-MIT.txt) |
| Noto Sans CJK KR 글꼴 및 웹용 서브셋 | [Noto CJK](https://github.com/notofonts/noto-cjk) | [Sans OFL](plugins/hermes_ext/fortune_oracle/fonts/NotoSans-OFL.txt), [웹 글꼴 OFL](web/fortune_web/static/fonts/OFL.txt) |
| Noto Serif CJK KR 글꼴 | [Noto CJK](https://github.com/notofonts/noto-cjk) | [Serif OFL](plugins/hermes_ext/fortune_oracle/fonts/NotoSerif-OFL.txt) |
| Pretendard Variable 웹 글꼴 | [orioncactus/pretendard](https://github.com/orioncactus/pretendard) | [Pretendard OFL](web/fortune_web/static/fonts/Pretendard-OFL.txt) |

한국 음력 입력 변환은 [korean-lunar-calendar](https://pypi.org/project/korean-lunar-calendar/) 0.4.0 (MIT)을 사용합니다. 소스나 역법 표를 복사하지 않고 Python 의존성으로 설치합니다. 검증 범위와 한국/중국 달력 차이는 [한국 음력 입력](docs/web-lunar-calendar.md)에 기록합니다.

Python 의존성은 각 requirements 파일, Node 의존성은 [package-lock.json](plugins/hermes_ext/fortune_oracle/scripts/package-lock.json)에 선언되어 있습니다. 의존성 배포물은 이 소스 후보본에 복사하지 않습니다. 설치하거나 묶어 배포할 때 해당 배포물의 라이선스·저작권 고지를 함께 확인하고 보존해야 합니다.

선택적 `pyswisseph` 및 Swiss Ephemeris의 조건과 미해결 범위는 [설치 안내](docs/PUBLIC_SETUP.md#선택적-계산과-라이선스-경계)와 [의존성 선언](plugins/hermes_ext/fortune_oracle/vedic-requirements.txt)에 기록되어 있습니다.
