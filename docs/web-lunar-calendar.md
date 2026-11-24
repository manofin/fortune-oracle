# 웹 한국 음력 출생일 입력

## 계약과 범위

- 본인 출생정보와 상대 궁합 입력에 `birth_calendar: "solar" | "lunar"`, `birth_leap_month: boolean`을 추가했다. 생략하면 양력·평달이다. 윤달은 음력에만 허용하며 문자열/숫자 boolean은 받지 않는다.
- 요청의 `birth_date`는 선택한 달력의 날짜다. 응답/저장 프로필의 `birth_date`는 **계산용 양력**이고, `birth_date_input`은 입력한 날짜, `birth_calendar`와 `birth_leap_month`는 원래 달력 정보다. 수정 요청은 `birth_date_input`을 요청의 `birth_date`로 보내야 한다. 응답 전체를 요청으로 되돌리지 않는다. 클라이언트가 계산용 날짜나 원본 메타데이터를 덮어쓰는 별도 필드는 받지 않는다.
- 기존 프로필은 읽을 때 양력 기본 메타데이터를 보충한다(조회만으로 DB를 변경하지 않음). 웹 수정 폼은 원본 날짜를 표시하며, 저장을 반복해도 재변환하지 않는다. 상대 입력은 기존처럼 요청 후 초기화하고 저장하지 않는다.
- 한국 음력 변환 지원 범위는 **음력 1900-01-01~2050-11-18**이다. 라이브러리의 더 넓은 과거 범위를 제품 지원으로 주장하지 않는다. 출생일 저장에는 추가로 **변환한 양력 날짜가 서버의 오늘을 넘지 않아야 한다**는 기존 제한을 적용한다. 양력 입력은 기존 1800년 이후 제한을 유지한다.
- 한국 음력 달력일만 양력 달력일로 바꾼다. 시각과 IANA 시간대는 바꾸지 않는다. 변환 후 기존 `BaziInput`에 전달하므로 DST 중복/누락 시각 검증과 일진 계산은 같은 양력 입력과 같다. 중국 음력, 타국 현지 음력, 태양시 보정, 자미두수 역법 변경은 이 기능의 범위가 아니다.
- 음력 2월 30일은 유효할 수 있어 음력 선택 시 HTML `date` 대신 `text` + YYYY-MM-DD 패턴을 사용한다. 유효한 월일과 실제 윤달 여부는 서버에서 확인한다. 양력으로 돌아가면 윤달을 해제하고 `date` 제약을 복구한다.

## 구현 의존성과 실제 의미 확인

`korean-lunar-calendar==0.4.0`(MIT)을 고정했다. 오프라인 표 기반이며 런타임 네트워크를 사용하지 않는다. 설치된 `setLunarDate`와 `__checkValidDate`를 읽고 확인했다: 불가능한 월일·범위 밖 날짜·실제 윤달과 다른 윤달 요청은 `False`를 반환한다. 변환기는 요청마다 새 객체를 만들며 실패 시 이전 날짜를 재사용하지 않는다. 추가로 설정된 연/월/일/윤달 값이 요청과 일치하는지 확인한다.

기존 Node `lunar-javascript`의 `Lunar.fromYmd`는 윤달을 음수 월로 받는다. 그러나 **한국 음력 입력 변환기로 대체 사용할 수 없다**. 실제 비교:

| 입력 | 한국 변환기 0.4.0 | 기존 lunar-javascript |
| --- | --- | --- |
| 2017 윤5월 1일 | 2017-06-24 | `wrong lunar year 2017 month -5` |
| 2017 윤6월 1일 | 거절 | 2017-07-23 |

이는 아래 KASI 공식 월력요항과 비교했다. 사주 엔진 자체는 변경하지 않고 양력 정규화 경계만 추가했다.

## 독립 기준 자료

테스트 기대 날짜는 라이브러리로 생성하지 않고 다음 한국천문연구원 자료와 대조했다. 테스트 날짜는 모두 합성 사례이며 개인 출생정보가 아니다.

1. [2017년 공식 월력요항 — 음력·양력 대조표](https://astro.kasi.re.kr/kor/life/post/almanac?search_year=2017): 평5월 1일→5월 26일, **윤5월 1일→6월 24일**, 평6월 1일→7월 23일, 12월 1일→2018년 1월 17일. 윤5월은 소월(29일)이다. 한국/중국 윤달 차이와 양력 연도 경계를 검증한다.
2. [2023년 달력자료](https://astro.kasi.re.kr/kor/life/post/calendarData?search_year=2023): 1월 1일→1월 22일, 평2월 1일→2월 20일(대월), 윤2월 1일→3월 22일(소월), 12월 1일→2024년 1월 11일(대월). 따라서 평2월 30일→3월 21일, 윤2월 29일→4월 19일, 12월 30일→2024년 2월 9일도 검증한다.
3. [2024년 달력자료](https://astro.kasi.re.kr/kor/life/post/calendarData?search_year=2024): 1월 1일→2월 10일, 2월 1일→3월 10일, 12월 1일→12월 31일. 3월 10일은 뉴욕 DST 공백 시각 검증에도 사용한다.

자료 2·3은 KASI가 게시했지만 페이지에서 **공식 발표 전 달력자료**라고 명시한다. 공식 월력요항과 혼동하지 않는다. 일부 추출 결과의 공통 팝업에 `Permission denied`가 섞였지만 해당 연도의 대조표 본문을 실제로 읽었다. 2017 공식 자료는 별도로 확인했다.

**한계:** 독립 대조는 위 사례에 대한 표본 검증이지 1900~2050년의 모든 날짜를 KASI와 전수 대조한 인증이 아니다. 범위 내 나머지 날짜는 고정된 한국 달력 라이브러리 표를 신뢰한다. 실제 iOS/Safari나 화면 낭독기 검증은 하지 않았다.

## 검증 실행

공개 설치 안내대로 Python 웹 개발 의존성 및 Node 의존성을 설치한 뒤 실행한다. 외부 LLM/운영 저장소는 사용하지 않는다.

```sh
python scripts/run_fortune_tests.py tests/test_fortune_oracle_web_lunar.py tests/test_fortune_oracle_web.py tests/test_fortune_oracle_web_schema.py tests/test_fortune_oracle_web_security_boundaries.py tests/test_fortune_oracle_web_situations.py tests/test_fortune_oracle_web_feature_flags.py tests/test_fortune_oracle_web_integrated.py
# 브라우저 검사는 자체 loopback 임시 서버를 실행하므로 network-denying runner와 별도로 실행한다.
env -i HOME="$HOME" PATH="$PATH" TMPDIR="$TMPDIR" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=plugins PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider scripts/check_fortune_web_lunar_browser.py
```

- TDD: 첫 API 테스트가 신규 필드 거절로 실패한 뒤 통과. 첫 브라우저 테스트가 달력 선택자 부재로 실패한 뒤 통과. 기존 프로필 조회 테스트가 메타데이터 `KeyError`로 실패한 뒤 통과.
- 실제 사주 차트와 오늘 풀이, 시간대별 날짜 범위를 음력/동등한 양력으로 비교한다. 한국/뉴욕 두 시간대, 평달·윤달·연도 경계를 포함한다.
- HTTP 저장/조회/수정, 기존 프로필 기본값, 잘못된 음력/윤달/형식 요청이 저장 정보를 바꾸지 않는지, 상대 궁합 결과 동등성을 검증한다.
- Chromium 320/390/1280px에서 음력 등록→새로고침→원본 재편집→상대 윤달→양력 초기화 경로, 수평 넘침, JS 오류 0 및 외부 요청 0을 확인한다. 합성 폼 화면만 선택적으로 `LUNAR_SCREENSHOTS` 디렉터리에 저장한다.
