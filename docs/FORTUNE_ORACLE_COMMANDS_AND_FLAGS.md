# Fortune Oracle Commands and Flags

이 문서는 Hermes 명령 어댑터의 소스 계약이다. 기본 웹 실행에는 gateway가 필요하지 않다. 명령이 존재한다는 사실은 특정 봇에 배포되었다는 뜻이 아니다.

## 명령

| 명령 | 동작 |
| --- | --- |
| `/today_fortune`, `/tomorrow_fortune` | 등록 정보와 사용자 시간대의 날짜로 풀이. 계산 불가와 일반 문구를 계산 결과로 표시하지 않는다. |
| `/month_kline`, `/life_kline` | 월간·인생 흐름 텍스트. 해석 지수는 경험적 지표다. |
| `/kline_card`, `/kline_card year` | 월간·연간 PNG 카드. 파일명과 caption에 출생 원문을 넣지 않는다. |
| `/register_birth` | 한 줄로 출생정보를 등록한다. multi-turn 등록은 지원하지 않는다. |
| `/show_profile`, `/profile_status` | 요약과 필드 존재 여부를 조회한다. 원문 민감값은 출력하지 않는다. |
| `/delete_profile` | 확인 안내. `/delete_profile 확인`으로 해당 프로필 삭제를 요청한다. |
| `/deep_fortune`, `/deep_fortune full`, `/deep_fortune qna` | opt-in 심층 풀이. 기본 비활성이면 외부 모델 없이 fallback한다. |
| `/voice_fortune` | 지원 환경에서 음성, 그 외 텍스트 fallback. |
| `/도움말` | 한국어 사용 안내. |

## 환경변수

- `FORTUNE_DEEP_ANALYSIS`: 정확히 `1`일 때만 직접 심층 명령의 provider 경로를 연다. 기본 OFF.
- `FORTUNE_DEEP_PROVIDER`: 로컬 호환 adapter를 선택할 때 `local_openai_compatible`.
- `FORTUNE_DEEP_BASE_URL`: 운영자가 지정하는 endpoint. 미설정·공백이면 호출을 막는다. 이 문서는 동작하는 운영 주소를 제공하지 않는다.
- `FORTUNE_DEEP_MODEL`, `FORTUNE_DEEP_MODEL_LABEL`: 선택한 모델과 출력 출처 라벨. 자신의 provider 설정과 맞춘다.
- `FORTUNE_DEEP_TIMEOUT_SEC`: provider timeout, 기본 30초.
- `FORTUNE_DEEP_QOPUS_API_KEY`: 호환 endpoint 자격증명. 실제 값은 private `runtime.env`에 보관하고 기본값을 운영 인증수단으로 쓰지 않는다.
- `FORTUNE_PUBLIC_TELEGRAM`: 정확히 `1`일 때 Fortune 전용 공개 native handler를 등록한다. 일반 agent 권한 개방 설정이 아니다.
- `FORTUNE_DAILY_ENABLED`: 실제 일일 발송은 이 값 `1`과 실행 시 `--send`를 함께 요구한다. 기본은 dry-run이다.

웹 전용 변수와 기본 비활성 기능은 [웹 안내](../web/README.md)에 정리했다. 환경변수 목록만으로 활성화를 권장하거나 서비스 설정을 변경하지 않는다.

## 변경 경계

- No config.yaml auto modification. 기존 `config.yaml`을 자동 수정하지 않는다.
- `/show_profile`, `/life_kline`, `/today_fortune`에 심층 결과를 자동으로 붙이지 않는다.
- LINE remains deferred. `LINE_PUBLIC_URL`이나 LINE 공개 경로를 제공하지 않는다.
- live gateway 재시작·서비스 변경은 운영자의 명시적 승인 범위에서만 수행한다.
