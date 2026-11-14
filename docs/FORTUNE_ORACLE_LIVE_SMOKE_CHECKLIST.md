# Fortune Oracle Live Smoke Checklist

먼저 [로컬 설치·검증](PUBLIC_SETUP.md)을 완료한다. 기본 검증은 임시 DB/store와 합성 프로필로 실행한다. 이 체크리스트는 특정 운영 서비스에 접속하거나 실사용자 자료를 읽으라는 지시가 아니다. LINE remains deferred.

## 로컬 확인

1. `/도움말`: 프로필·심층 명령과 한 줄 등록, multi-turn 미지원 안내를 확인한다.
2. `/profile_status`: 미등록 상태에는 원문 출생정보가 없고 등록 후에도 presence/masked 값만 나온다.
3. `/show_profile`: 요약이 표시되며 birth_date/birth_time/name_hanja 원문이 없다.
4. `/life_kline`: 텍스트가 표시되고 외부 심층 풀이가 자동으로 붙지 않는다.
5. `/kline_card`, `/kline_card year`: PNG가 생성되고 파일명·caption에 개인자료가 없다.
6. `/deep_fortune full`, `/deep_fortune qna`: 기본 OFF에서 provider 호출이 없고 결정적 fallback이 표시된다.
7. 합성 성인 프로필 한 줄 등록: 성별 토큰이 표시 이름에 섞이지 않고, 시각 미상과 `00:00`을 구분한다.
8. 임시 store를 저장·다시 로드해 같은 경로를 호출한다. 메모리 mock만으로 저장 형식 호환을 판정하지 않는다. 원문 store를 출력할 필요는 없다.
9. 신뢰된 context의 서로 다른 두 합성 사용자로 조회·수정·삭제 격리를 확인한다. 식별자 부재 시 다른 저장 프로필을 선택하지 않는지 확인한다.

## 삭제·운영 확인

`/delete_profile` 또는 `사주삭제 확인`의 실제 운영 자료 삭제는 **explicit user approval** 이후에만 수행한다. 승인된 대상과 복구 정책을 먼저 정한다. 로컬 테스트에서는 폐기 가능한 임시 store만 사용한다. 백업을 만들더라도 저장소·로그·테스트 산출물에 넣지 않는다.

실제 Telegram 확인은 테스트 전용 계정과 승인된 환경에서 별도로 수행한다. 로컬 테스트 성공을 실제 다중 계정 격리나 메시지 도착의 증거로 쓰지 않는다. 프로필 키는 `telegram:<user_id>`이며 legacy `telegram:default` 자료의 이관은 별도 [이관 계획](FORTUNE_ORACLE_PROFILE_KEY_MIGRATION_PLAN.md)을 따른다.

## 재시작과 복구

Python 소스를 수정해도 실행 중인 gateway에 즉시 반영되지 않을 수 있다. stale handler라면 플러그인 등록과 로드된 버전을 확인한다. live gateway 재시작·reload는 명시적으로 승인된 경우에만 한다. 이 후보본 설치나 문서 검토는 기존 서비스의 재시작 권한을 뜻하지 않는다.

이 검증 때문에 gateway/run.py, gateway/platforms/*, config.yaml, 기존 cron/systemd나 Hermes core를 자동 수정하지 않는다. 결과 보고에는 수행 범위·성공/실패·재시작 여부만 기록하고 실제 사용자 ID·출생정보·토큰·운영 URL·PID를 넣지 않는다.
