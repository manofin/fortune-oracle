# 공개 후보본 설치와 검증

이 안내는 개발자가 별도 환경에서 소스를 복원하는 절차다. 특정 운영 호스트, 현재 배포, 사용자 데이터나 비밀 설정을 전제로 하지 않는다. 명령은 저장소 루트에서 실행한다.

## 기본 웹 환경

Linux/Unix 환경에서 Python 3.14, Node.js 22와 npm을 준비한다. 파일 잠금에 `fcntl`을 사용하므로 Windows는 WSL 등 Linux 환경이 필요하다. 기본 웹은 Flask/Gunicorn과 Node 계산 브리지를 사용한다. Hermes gateway 전체 설치, Telegram 계정, 외부 모델은 기본 웹 미리보기에 필요하지 않다.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r web/requirements.txt
npm ci --prefix plugins/hermes_ext/fortune_oracle/scripts --ignore-scripts
.venv/bin/python web/preview.py
```

미리보기는 `127.0.0.1:8765`에만 바인딩하고 임시 DB와 매번 새 비밀키를 만든다. 종료 시 임시 DB를 지운다. 등록 시험에는 가상 성인 프로필만 사용한다. 운영 DB나 기존 Telegram store를 연결하지 않는다. 다른 포트는 `--port`로 지정할 수 있다.

Python 의존성과 Node 의존성은 별개다. Python 설치만으로 `lunar-javascript`와 `iztro`가 설치되지 않으므로 위 `npm ci --prefix plugins/hermes_ext/fortune_oracle/scripts`를 생략하지 않는다. 잠금 파일을 임의로 재생성하거나 `node_modules`를 저장소에 복사하지 않는다.

## 개발 검증

기본 회귀 검사는 Python 3.14와 Node.js 22를 기준으로 한다. 새 venv에 고정된 테스트 의존성을 설치하고, 위의 `npm ci`도 실행한다. 음성 계약 검사는 로컬에서 만든 합성 음원을 `ffmpeg`/`ffprobe`로 확인하므로 두 도구도 필요하다. Ubuntu/Debian에서는 `sudo apt-get install ffmpeg`로 설치할 수 있다. 실제 음성 합성 서비스나 계정은 사용하지 않는다.

```bash
.venv/bin/python -m pip install -r web/requirements-test.txt
.venv/bin/python -B scripts/run_fortune_tests.py --profile core
.venv/bin/python -B scripts/run_fortune_tests.py --profile guard
```

`core`는 웹 HTTP·세션·삭제·공유·보안 경계와 실제 Node 계산, 엔진·렌더링 계약을 검사한다. 선택적 천체 계산을 요구하는 **정확히 16개 테스트**만 별도 `astronomy` 프로필로 분리한다. 해당 모듈의 의존성 누락·개인정보·부분 계산 검사들은 계속 core에서 실행된다. 분리 목록의 테스트가 삭제되거나 이름이 바뀌면 collection을 실패시켜 목록 수정을 요구한다. 요구 패키지나 잠금 파일과 일치하는 Node 브리지가 없으면 설치 명령과 함께 중단한다. 테스트용 Python 의존성은 전이 의존성까지 고정하며, Node 설치에서는 패키지 lifecycle script를 실행하지 않는다.

`guard`는 공개 파일·비밀값 검사기의 가상 저장소 회귀를 따로 실행한다. core에서 허용하는 skip은 격리된 `HERMES_HOME`에 외부 Hermes checkout이 없음을 확인하는 한 계약뿐이다. 그 밖의 skip은 프로필 명령을 실패시킨다. `astronomy`와 `guard`는 skip을 허용하지 않는다. 각 프로필은 선택·제외 수와 skip 사유를 출력한다. CI의 [Core and guard tests](../.github/workflows/core-tests.yml)는 push/PR마다 Python 3.14 core·guard와 별도 Python 3.11 astronomy job을 실행한다.

일부 파일만 확인할 때는 기존 명령을 쓸 수 있다. 명시적 파일 선택에는 프로필의 분리 목록을 적용하지 않으므로 선택적 실제 계산 assertion도 그대로 실행되어 준비가 안 된 환경에서는 실패할 수 있다.

```bash
.venv/bin/python -B scripts/run_fortune_tests.py tests/test_fortune_oracle_web.py \
  tests/test_fortune_oracle_web_metrics.py tests/test_fortune_oracle_web_situations.py
```

runner는 임시 `HERMES_HOME`과 store를 만들고 종료 시 지운다. 상속된 Fortune 사용자·세션·API 비밀값·pytest 외부 플러그인 설정을 제거하고 checkout의 플러그인만 import한다. 실제 Python 소켓 연결과 runtime TTS를 차단하며, 코드가 연결 예외를 잡더라도 연결 시도 자체가 있으면 실패한다. 테스트에는 운영 비밀값이나 실사용자 자료를 준비하지 않는다. matplotlib/Pillow는 PNG 회귀용이며 기본 웹 의존성이 아니다.

브라우저 검사는 별도 추가 항목이다. Playwright/Chromium을 설치한 뒤 별도 터미널에서 실행 중인 로컬 임시 미리보기에만 연결한다.

```bash
.venv/bin/python -m pip install -r web/requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/check_fortune_web_browser.py --output /tmp/fortune-web-browser
```

기본 브라우저는 Chromium이다. 홈·상품 샘플·공유·성장 경로 검사 스크립트에는 `--browser chromium|firefox|webkit`을 지정할 수 있다. 추가 엔진은 `.venv/bin/python -m playwright install firefox webkit`으로 준비하고, 호스트의 브라우저 실행 의존성도 충족해야 한다. 각 실행은 별도 출력 디렉터리를 사용하며, 실제 운영 주소가 아닌 `local-preview` 버전의 loopback 미리보기에만 연결한다. 결과에는 실제 엔진 버전을 기록한다. Linux WebKit의 휴대폰 화면 검사는 실제 iPhone Safari 검증이 아니며, Firefox는 화면 크기·터치만 모사한다. OS 공유와 클립보드는 자동 검사에서 제어한 대역을 사용한다.

이 절차의 안내가 모든 테스트를 실행했다는 증거는 아니며, 테스트 결과는 실행한 환경에서 확인한다.

## 선택적 계산과 라이선스 경계

기본 웹과 선택적 통합 계산 환경을 구분한다. 통합 기능과 출생 위치 수집은 기본 비활성이다. 기존 선택적 runtime 의존성 선언은 `web/requirements-integrated.txt`이며 기본 core 환경에는 설치하지 않는다. 아래 astronomy 회귀용 venv는 별도의 테스트 환경이며 공개 기능 활성화나 runtime 선언 변경을 뜻하지 않는다.

`ephemeris-requirements.txt`와 `vedic-requirements.txt`는 선택적 천체 계산 의존성을 선언한다. 전자는 Skyfield 계열, 후자는 `pyswisseph` 바인딩을 포함한다. 외부 천체력 파일이 필요한 경로는 개발자가 별도로 준비해야 하며, 이 후보본은 운영 캐시·천체력 파일·vendor 디렉터리를 제공하지 않는다. 자료가 없을 때의 계산 불가를 정상 결과로 바꾸지 않는다.

선택적 계산 전체를 기본 웹 설치만으로 검증할 수는 없다. Python 3.14 검증 환경에서는 고정 버전 `pyswisseph==2.10.3.2`의 native wheel 빌드가 실패했다. [이 버전의 공식 배포 파일](https://pypi.org/project/pyswisseph/2.10.3.2/#files)은 CPython 3.11까지의 wheel을 제공하지만, 기존 runtime의 [NumPy 2.5.3](https://pypi.org/project/numpy/2.5.3/)은 Python 3.12 이상을 요구한다. runtime 선언을 그대로 Python 3.11에 설치하는 방식은 호환되지 않는다.

회귀용 [requirements-astronomy-test.txt](../web/requirements-astronomy-test.txt)는 같은 Swiss 바인딩과 Skyfield 버전에 Python 3.11을 지원하는 [NumPy 2.3.5](https://pypi.org/project/numpy/2.3.5/)를 별도로 고정한다. Linux x86-64, CPython 3.11.15에서 wheel만으로 설치하고 16개 계산 회귀를 skip 없이 검증한 조합이다. Python 3.14 core venv와 섞지 않는다. Node 브리지는 위의 `npm ci --ignore-scripts`로 준비한다.

다음 절차에서 천체력 파일은 checkout 밖에 저장한다. provisioning 명령은 NASA 공개 파일만 명시적으로 내려받고 **32,726,016 bytes**와 SHA-256 `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2`를 검증한다. 기존 파일은 hash가 맞으면 그대로 쓰고 다르면 덮어쓰지 않는다. 테스트 명령은 네트워크를 사용하지 않으며, `--ephemeris`의 로컬 파일과 두 계산 백엔드가 없거나 손상됐으면 pytest 실행 전에 준비 오류로 중단한다. 상속된 `FORTUNE_EPHEMERIS_PATH`는 신뢰하지 않는다.

```bash
python3.11 -m venv .venv-astronomy
.venv-astronomy/bin/python -m pip install --only-binary=:all: -r web/requirements-astronomy-test.txt
FORTUNE_TEST_EPHEMERIS_DIR="$(mktemp -d /tmp/fortune-ephemeris.XXXXXX)"
PYTHONPATH=plugins .venv-astronomy/bin/python -m hermes_ext.fortune_oracle.ephemeris_setup \
  --output "$FORTUNE_TEST_EPHEMERIS_DIR/de440s.bsp"
.venv-astronomy/bin/python -B scripts/run_fortune_tests.py --profile astronomy \
  --ephemeris "$FORTUNE_TEST_EPHEMERIS_DIR/de440s.bsp"
```

`astronomy`는 목록에 든 5개 모듈만 수집하고 NASA 기준 경도·하우스·시간대, Swiss 수치 회귀, 실제 통합 풀이의 계산 출처를 확인하는 16개 assertion을 실행한다. 의존성 부족을 skip이나 성공 결과로 바꾸지 않는다. 공개 NASA fixture의 두 시점·다섯 천체 비교는 최대 경도 잔차 약 `0.0000151°`로 기존 허용치 `0.001°` 안에 들었다. 이는 계산 구현의 회귀 근거이며 운세 해석의 예측 정확도를 검증하지 않는다. 테스트가 끝나면 위 명령이 만든 임시 천체력 디렉터리만 삭제할 수 있다.

기문 계산도 선택 사항이다. 관련 버전과 네이티브 의존성은 [플러그인 의존성 선언](../plugins/fortune_oracle_plugin/runtime-requirements.txt)에 있으며, 기본 웹 설치에는 `kinqimen`을 추가하지 않는다. 모듈 격리 단위검사 통과가 실제 기문 계산의 검증을 뜻하지는 않는다.

기존 의존성 고지는 `pyswisseph`의 AGPL-3.0과 Swiss Ephemeris의 AGPL/Professional 선택지를 명시한다. **Swiss Ephemeris Professional 라이선스가 Python 바인딩까지 재허가한다고 가정하지 않는다.** 적용 방식과 상용 이용은 아직 결정되지 않았다. 정확한 범위는 [기존 의존성 선언](../plugins/hermes_ext/fortune_oracle/vedic-requirements.txt)과 해당 배포물의 고지에서 확인한다. 베딕 기능을 공개 서비스에서 활성화하거나 판매하려면 이 미해결 사항을 먼저 정리해야 한다. 이는 코드 후보본을 공개 검토하는 작업과 별개의 결정이다.

루트 프로젝트 라이선스는 이 준비 작업에서 새로 부여하지 않는다. Node 패키지, 글꼴 등 제3자 자료의 고지와 라이선스도 각각 유지해야 한다.

## 비공개 runtime.env

`.env.example`은 값이 없는 참고 목록이며 앱이 자동으로 읽지 않는다. 실제 비밀값은 **소스 트리 밖의 `runtime.env`**에 두고 소유자만 읽도록 한다. DB·백업·로그도 소스 밖에 보관한다. 테스트에는 운영 비밀값이나 실사용자 자료를 복사하지 않는다.

다음 예시는 새 파일에만 쓰며 비밀값을 화면에 출력하거나 CLI 인자로 전달하지 않는다. 기존 파일이 있으면 중단하므로 덮어쓰지 않는다. 예시 origin은 실제 운영 origin으로 교체하기 전에는 서비스용으로 사용할 수 없다.

```bash
python3.14 - <<'PYENV'
import json
import os
from pathlib import Path
import secrets

runtime = Path.home() / ".local/state/fortune-oracle"
runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
runtime.chmod(0o700)
(runtime / "data").mkdir(exist_ok=True, mode=0o700)
values = {
    "FORTUNE_WEB_SECRET": secrets.token_hex(32),
    "FORTUNE_WEB_STORE": str(runtime / "data/web.sqlite3"),
    "FORTUNE_WEB_VERSION": "local-unpublished",
    "FORTUNE_WEB_PUBLIC_ORIGIN": "https://example.invalid",
}
fd = os.open(runtime / "runtime.env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    for key, value in values.items():
        stream.write(f"{key}={json.dumps(value)}\n")
PYENV
```

파일은 화면·셸 기록·로그를 공유하지 않는 로컬 편집기로 관리한다. `cat`, 환경 덤프, `set -x`, 비밀값을 포함한 실행 인자, 저장소에 복사한 `.env`는 사용하지 않는다. 서비스 관리자가 `EnvironmentFile`로 파일을 읽게 하고, 앱에는 환경변수로 전달한다. 미리보기는 위 운영 설정이 필요 없다.

## 서비스 준비

1. 소스·venv·Node 의존성과 쓰기 가능한 DB 디렉터리를 분리한다.
2. `web/deploy/fortune-oracle-web.service`는 템플릿이다. `@RUNTIME@`과 `@NODE_DIR@`을 자신의 경로로 바꾸고 `EnvironmentFile`이 비공개 `runtime.env`를 가리키는지 확인한다. 쓰기 허용 경로도 실제 DB 위치에 맞춘다.
3. 비밀키는 32자 이상 무작위 값, store는 웹 전용 절대 경로, version은 배포한 소스 식별자로 지정한다. 실제 HTTPS origin은 경로·사용자정보 없는 정확한 origin이어야 한다.
4. HTTPS reverse proxy 뒤에서 backend를 loopback에만 바인딩한다. 기본 쿠키는 Secure/HttpOnly/SameSite=Lax다. 클라이언트의 X-Forwarded-*를 신뢰하지 않는다.
5. Gunicorn은 하나의 worker와 여러 threads 구성을 사용하며 `--preload`는 사용하지 않는다. 만료 정리 스레드가 앱 시작 후 실행되어야 한다. 접근 로그에는 개인정보가 남지 않도록 한다.

템플릿 설치·서비스 시작·방화벽·외부 노출은 이 문서 작성으로 수행되지 않는다. 개발용 미리보기를 공개 서버로 쓰지 않는다. Python/Node subprocess가 필요한 현재 서버는 Worker 전용 호스팅에 그대로 올릴 수 없다.

## 공개 후보본의 이력

기존 비공개 저장소의 새 브랜치로 공개하지 않는다. 허용 파일만 추린 폴더에서 **부모 커밋이 없는 새 저장소**를 시작하고, 기존 `.git`, 커밋·태그·remote를 옮기지 않는다. 실제 게시 전에는 권리자의 루트 라이선스 선택, 파일 목록·비밀값·개인정보·제3자 고지 검토가 필요하다. 이 후보본에는 운영 확인 보고서와 과거 사고 상세를 포함하지 않는다.
