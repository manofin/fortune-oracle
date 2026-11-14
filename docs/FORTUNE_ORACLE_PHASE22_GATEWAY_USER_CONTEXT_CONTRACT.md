# Gateway User Context Contract

이 문서는 어댑터가 신뢰할 사용자 context를 받는 경계와 호환 조건을 기록한다. 과거 설계 단계를 특정 gateway 버전의 구현 완료 증거로 사용하지 않는다. 이 소스에는 사용자별 프로필 키 해석이 있으나, 사용하는 Hermes gateway의 context 전달과 실제 다중 계정 격리는 별도로 검증해야 한다.

## 입력 계약

legacy handler는 `fn(args: str) -> str` 형식이다. 문자열 인자만으로는 안전한 사용자 식별자를 얻을 수 없다. 새 handler의 `fn(args, context)`가 다음 값을 받는 형태를 기준으로 한다.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PluginContext:
    platform: str
    user_id: str | None = None
    chat_id: str | None = None
    session_id: str | None = None
    message_id: str | None = None
```

이 예시는 gateway가 실제로 전달하는 스키마를 대체하지 않는다. legacy `fn(args)`는 `context=None` 어댑터로 호환할 수 있지만 식별자 없는 호출에 기존 저장 프로필을 임의로 붙이지 않는다.

## 신뢰 경계

- 프로필 키 `telegram:<user_id>`는 gateway가 검증한 platform/user_id로만 구성한다.
- 메시지 본문, 명령 인자, 임의의 chat_id를 사용자 신원으로 사용하지 않는다.
- 식별자가 없거나 context가 불완전하면 다른 저장 프로필을 자동 선택하지 않는다.
- 사용자 ID·세션 ID·프로필 값은 로그나 공개 검증 보고서에 출력하지 않는다.

## 통합 확인 순서

1. 사용하는 gateway의 context 스키마와 어댑터를 확인한다.
2. 서로 다른 합성 사용자로 등록·조회·삭제 격리와 식별자 부재 실패 경로를 테스트한다.
3. legacy store가 있다면 [이관 계획](FORTUNE_ORACLE_PROFILE_KEY_MIGRATION_PLAN.md)의 Dry-run을 수행한다.
4. 실제 서비스 확인이나 자료 이관은 승인된 범위에서 별도로 한다.

## 이 후보본의 변경 경계

- No gateway/run.py edits.
- No gateway/platforms/* edits.
- gateway core 확장이나 파괴적 자료 이관은 이 문서로 수행되지 않는다.
