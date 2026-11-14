# Fortune Oracle 제품·명령 계약

모바일 웹과 Hermes 명령 어댑터의 소스 기능을 설명한다. 공개 후보본은 운영 배포·보안 인증·제품 검증 완료를 뜻하지 않는다. 재현 절차는 [설치 안내](PUBLIC_SETUP.md), 웹 API와 데이터 경계는 [웹 안내](../web/README.md)를 따른다. LINE is intentionally deferred.

## 웹 기능

폼 등록 → 프로필 저장 → 오늘·내일·월간 풀이 → 조회·삭제를 제공한다. 기본 웹은 기존 사주 계산 엔진을 사용하고 외부 모델을 호출하지 않는다. 계산값·경험적 해석·계산하지 못한 상태를 구분한다. 출생시각 미상은 허용하며 계산하지 않은 시주나 대운을 채우지 않는다.

웹 프로필은 별도 SQLite의 서버 발급 브라우저 세션에 연결한다. 현재 세션 유효기간은 90일이고 계정·기기 간 복원은 없다. 등록 전 이 제한을 알린다. 궁합 상대 정보는 요청 중 비교에만 쓰며 DB에 저장하지 않는다. D-day는 사용자 시간대의 오늘부터 365일 뒤까지이며 성공 확률을 제공하지 않는다.

공유 PNG에는 날짜·키워드·해석 지수만 담는다. 이름·출생 원문·팔자는 넣지 않으며 공유 내용도 출생정보에서 파생된 자료이므로 익명 정보라고 부르지 않는다. 공통 OG 소개와 고정 유입 표식 `?from=card`만 사용하고 개인 결과 URL·발신자 ID는 만들지 않는다. 유입은 일별 브라우저 세션 집계이며 실제 게시·추천 전환율을 뜻하지 않는다.

상품 샘플은 가상 편집 예시와 가설 가격이다. 샘플은 실제 네 체계 계산 결과나 판매 가능한 상품을 뜻하지 않는다. 결제·예약·출시 알림·장기 계정·기기 간 복원은 제공하지 않는다.

## Hermes 명령 계약

아래 목록은 웹의 메뉴 목록과 별개다. 설치된 gateway의 handler/context 계약과 실제 동작은 해당 환경에서 확인한다.

- `/today_fortune`, `/tomorrow_fortune`: 등록 정보와 사용자 시간대의 날짜를 계산한다. 실패·미등록·일반 문구는 “계산 결과가 아님”으로 구분한다.
- `/month_kline`, `/life_kline`: 월간·인생 흐름 텍스트. 계산값과 경험적 해석 지수를 구분한다.
- `/kline_card`, `/kline_card year`: 월간·연간 PNG 카드. caption·파일명에 출생 원문을 넣지 않는다.
- `/register_birth`: 한 줄 출생정보·표시 이름·선택 성별 등록. Multi-turn registration unsupported.
- `/show_profile`: 등록 프로필 기반 요약. birth_date/birth_time/name_hanja 원문은 출력하지 않는다.
- `/delete_profile`: 확인 안내. `/delete_profile 확인`으로 요청한 사용자 프로필을 삭제한다.
- `/profile_status`: 등록 여부와 필드 presence/masked 값만 표시한다.
- `/deep_fortune`, `/deep_fortune full`, `/deep_fortune qna`: opt-in 심층 풀이. 기본 비활성이면 외부 provider 없이 fallback한다.
- `/ziwei_deep`: 기본 비활성. 켠 경우에만 프로필을 확인하고 계산 경로를 사용한다.
- `/daily_on [HH:MM]`, `/daily_off`: Telegram 개인 대화의 명시적 일일 수신 동의·해제.
- `/voice_fortune`: 지원 환경에서 TTS, 그 외 텍스트 fallback.
- `/도움말`: 한국어 도움말.

`FORTUNE_PUBLIC_TELEGRAM=1`의 Fortune 전용 공개 native handler는 일반 gateway 명령이나 agent 권한을 개방하지 않는다. 공개 경로의 심층·궁합·음성은 이용 불가 안내를 반환할 수 있다. 이 문서는 실제 Telegram 두 계정 격리나 메시지 수신 검증의 증거가 아니다.

## 기본 비활성 기능

- `FORTUNE_DEEP_ANALYSIS=1`이 없으면 provider factory/call을 하지 않는다. provider URL이 미설정·공백이어도 호출을 막는다.
- 모델 서사는 외부 모델 해석으로 표시하고 provider/model 출처를 붙인다. 구조·타입 또는 금칙 표현 검증 실패 시 기본 풀이를 쓴다. 이 검증이 모든 의미 오류를 검출하지는 않는다.
- `FORTUNE_WEB_INTEGRATED_ENABLED`와 `FORTUNE_WEB_BIRTH_LOCATION_ENABLED`는 정확히 `1`일 때만 각 기능을 켠다. 서로 독립적이며 결제·유료 권한 검사가 아니다.
- LINE deferred. LINE 공개 URL이나 구현을 제공하지 않는다.

선택적 베딕 의존성의 라이선스와 상용 적용은 미해결이다. 코드 공개 검토, 서비스에서 기능을 켜는 결정, 상품 판매를 혼동하지 않는다. [선택적 의존성 안내](PUBLIC_SETUP.md)를 확인한다.

## 프로필·개인정보

표시 이름·출생일·출생시각·선택 출생지·시간대·성별·선택 한자명·허용된 생활 맥락을 다룬다. 파생 출생연도와 해석도 다른 자료와 결합하면 개인정보가 될 수 있으므로 비민감 또는 익명으로 단정하지 않는다.

- 시각 미상은 빈 문자열로 보존하고 임의의 자정으로 채우지 않는다. 명시한 `00:00`과 구분하며 잘못된 시간·분은 거절한다.
- 원문 birth_date/birth_time/name_hanja는 deep prompt, caption, PNG 파일명, provider 출처, 로그에 넣지 않는다.
- `/profile_status`는 masked/presence만, `/show_profile`은 허용된 요약만 출력한다. fallback에 dict/list/dataclass 원문 repr를 넣지 않는다.
- 생활 맥락은 `occupation_context`, `creative_context`, `recent_context`, `project_context` 허용 목록만 쓴다.
- 저장 키는 검증된 gateway platform/user_id의 `telegram:<user_id>`를 사용한다. 식별자가 없으면 다른 저장 프로필을 자동 선택하지 않는다.
- legacy `telegram:default`의 이관은 [별도 계획](FORTUNE_ORACLE_PROFILE_KEY_MIGRATION_PLAN.md)을 따른다. 실제 다중 계정 격리는 별도로 확인한다.

위 항목은 검증해야 할 계약이며 모든 운영 로그·캐시·외부 호출이 검증되었다는 선언은 아니다.

## 일일 발송 경계

수신 동의 시각과 다음 KST 날짜부터의 시작일을 저장한다. 아침 06:00–11:59(기본 08:00), 하루 최대 한 번이며 프로필이 없거나 동의 증거가 없으면 건너뛴다. 발송 직전 잠금 아래에서 동의·프로필·시각·중복 여부를 확인한다. 해제 성공 이후 새 발송을 시작하지 않지만 이미 전송 중인 메시지는 취소할 수 없다.

Telegram 호출 전 시도 상태를 fsync해 저장한다. 도착 여부가 불명확해도 같은 날 재시도하지 않아 중복 방지를 우선하며 무손실 전달은 보장하지 않는다. 중복 방지 기록은 사용자 키의 해시·날짜·상태·시각·성공 시 message ID를 사용한다. 해시는 익명화 보장이 아니며 공개 보고서에 실제 해시를 싣지 않는다. 이름·출생정보·본문·토큰을 복제하지 않는다. 당일 기록은 삭제·해제 후에도 유지하고 다음 KST 발송 작업에서 이전 날짜 기록을 지운다.

기본 실행은 dry-run이며 실제 발송은 `--send`와 `FORTUNE_DAILY_ENABLED=1`을 함께 요구한다. `--at`은 dry-run 전용이다. 실제 발송 검증이나 서비스 재시작은 운영자의 승인 범위에서만 수행한다.

## 한계와 검증

multi-turn 등록은 지원하지 않습니다. 대운 시작 나이는 근사값이며 진태양시·경도 보정은 지원하지 않는다. 용신은 규칙 기반의 낮음/중간 신뢰도 참고다. 점수·키워드는 경험적 해석이며 적중률·관계 성공 확률·의료·재무 판단을 제공하지 않는다.

로컬 fixture·HTTP·브라우저 검증과 실제 배포·실기기 공유·Telegram 수신 관찰은 구분한다. 오래된 Phase/PASS 숫자나 비공개 운영 보고서는 공개 후보본의 완료 증거로 인용하지 않는다. 검증 방법은 [smoke 체크리스트](FORTUNE_ORACLE_LIVE_SMOKE_CHECKLIST.md)를 따른다.
