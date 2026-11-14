"""Fortune Oracle — Deep Analysis Contract (Phase 11).

이 모듈은 실행 코드가 없는 순수 문서/타입 명세 모듈입니다.
실제 분석 로직은 deep_analyzer.py에 있습니다.

─────────────────────────────────────────────
OVERVIEW
─────────────────────────────────────────────

deep_analyze()는 provider function injection 방식으로만 LLM과 연결됩니다.
모듈 import 시 어떤 네트워크 클라이언트도 생성하지 않습니다.
기본값은 DISABLED입니다.

─────────────────────────────────────────────
ACTIVATION
─────────────────────────────────────────────

환경변수 방식 (프로세스 시작 전 설정):
    FORTUNE_DEEP_ANALYSIS=1

또는 코드에서 명시적으로:
    result = deep_analyze(bazi, enabled=True, provider=my_provider)

권장 방식: provider injection (환경변수 없이, 명시적 enabled=True).

─────────────────────────────────────────────
PROVIDER CONTRACT
─────────────────────────────────────────────

provider는 다음 시그니처를 가진 callable이어야 합니다:

    def my_provider(prompt: str) -> str:
        ...

요구사항:
- prompt(str)를 받아 응답 str을 반환
- JSON 형식 응답 권장 (스키마는 _RESPONSE_SCHEMA 참고)
- blocking 호출 허용 — timeout은 deep_analyzer가 threading으로 처리
- module import 시 생성 금지 (credential 접근 금지)
- 호출 시점에만 생성하거나 lazy init

금지:
- openai, anthropic, google.generativeai 등을 module level에서 import
- os.environ에서 API key를 module level에서 읽기
- requests.Session, httpx.Client를 module level에서 생성

예시 — Hermes provider (추후 사용자 검토 후 활성화):

    def hermes_provider(prompt: str) -> str:
        # Hermes runtime의 LLM 호출 인터페이스 — 사용자 검토 필요
        raise NotImplementedError("사용자가 직접 구현 후 주입")

─────────────────────────────────────────────
PROMPT INPUT CONTRACT
─────────────────────────────────────────────

prompt에 포함되는 정보:
    - 팔자 간지 (년/월/일/시 간지 문자열)
    - 띠 (zodiac)
    - 오행 분포 (목/화/토/금/수 개수)
    - 템플릿 분석 요약 (최대 100자씩)
    - K선 요약 텍스트 (최대 200자, 선택)
    - System prompt (안전 지침 포함)

prompt에 포함되지 않는 정보:
    - birth_date (원문 생년월일)
    - birth_time (원문 출생 시각)
    - birth_place (출생지)
    - name_hanja (한자 이름)
    - 주민번호, 전화번호 등 식별자
    - display_name (현재 미포함 — 익명 분석)

─────────────────────────────────────────────
OUTPUT CONTRACT
─────────────────────────────────────────────

provider는 다음 JSON을 반환해야 합니다:

{
  "ok": true,
  "source": "deep_provider",
  "sections": [
    {
      "title": "섹션 제목",
      "summary": "내용 (2-3문장)",
      "reflection_question": "자기성찰 질문 (없으면 빈 문자열)",
      "confidence": "llm",
      "disclaimer": ""
    }
  ],
  "warnings": [],
  "disclaimer": "이 분석은 오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다."
}

실패 시 deep_analyzer가 자동으로 template fallback을 반환합니다.

─────────────────────────────────────────────
FALLBACK MATRIX
─────────────────────────────────────────────

| 상황                        | 결과                   | source     |
|-----------------------------|------------------------|------------|
| enabled=False               | template               | template   |
| provider=None               | template               | template   |
| timeout 초과                | template + warning     | template   |
| provider exception          | template + warning     | template   |
| 빈 응답                     | template + warning     | template   |
| 과긴 응답 (>8000자)         | template + warning     | template   |
| JSON 파싱 실패              | template + warning     | template   |
| sections 없음               | template + warning     | template   |
| 안전 금지 패턴 감지         | llm + warnings[]       | deep_provider |

─────────────────────────────────────────────
SAFETY RULES (prompt 안에 포함됨)
─────────────────────────────────────────────

1. 오락과 자기성찰 용도 명시
2. 의학/투자/법률 결정 지시 금지
3. 불길한 단정/확정적 예언 금지
4. 특정 사건(사망/사고/질병) 예언 금지
5. 인간관계/건강/금전 확정적 예측 금지
6. 민감 정보 반복 출력 금지
7. 각 섹션 2-3문장 간결 작성
8. JSON 형식 응답만 허용

금지 패턴 (post-processing):
    "반드시 죽", "사망", "큰 사고", "파산", "이혼할 것",
    "병에 걸릴", "불치병", "당신은 곧", "의학적으로",
    "투자하세요", "법적으로", "소송에서 이길",
    "반드시 일어날", "피할 수 없는"

─────────────────────────────────────────────
LIVE ACTIVATION CHECKLIST (사용자 검토 항목)
─────────────────────────────────────────────

live 활성화 전 사용자가 직접 확인해야 하는 항목:

[ ] 1. 어떤 LLM provider를 주입할지 결정 (Hermes runtime / 외부 API / local)
[ ] 2. provider 함수 구현 및 테스트
[ ] 3. API 비용/rate limit 확인
[ ] 4. timeout 설정 적절성 확인 (기본 30초)
[ ] 5. 응답 품질 수동 검토 (fake provider 테스트 결과 확인)
[ ] 6. 안전 필터 충분성 검토 (금지 패턴 추가 필요 여부)
[ ] 7. Telegram /deep_fortune 명령 등록 여부 결정 (Phase 11에서 미등록)
[ ] 8. /life_kline 자동 append 여부 결정 (Phase 11에서 OFF)
[ ] 9. /show_profile 자동 append 여부 결정 (Phase 11에서 OFF)
[ ] 10. 운영 로그 레벨 설정 (민감 정보 log 제외 확인)

─────────────────────────────────────────────
CURRENT STATUS (Phase 11)
─────────────────────────────────────────────

- deep_analyze(): 구현 완료, 기본 OFF
- provider injection: 지원
- timeout: 30초 (threading)
- fallback: 완전 (모든 실패 경로 → template)
- /deep_fortune 명령: 미등록 (사용자 승인 후 추가)
- /life_kline deep append: OFF
- /show_profile deep append: OFF
- 외부 API client: import 없음
- 테스트: fake provider 기반 (실제 LLM 미사용)
"""

# 이 모듈은 실행 코드가 없습니다.
# 타입 import만 허용합니다.
from typing import Dict, List, Optional  # noqa: F401
