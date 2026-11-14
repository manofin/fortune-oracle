# Fortune Oracle

사주 계산과 풀이를 제공하는 Python/Node.js 프로젝트입니다. 모바일 웹과 Hermes용 명령 어댑터를 포함합니다. 계산값, 경험적 해석, 계산하지 못한 결과를 구분하며 외부 모델 해석은 기본 비활성입니다.

현재 개발 저장소는 **[manofin/fortune-oracle](https://github.com/manofin/fortune-oracle)**이며 기본 브랜치는 `main`입니다. 운영 데이터·비밀 설정·과거 비공개 Git 이력을 분리한 공개 소스입니다. 개인 기준 연구 fixture와 그에 의존하는 회귀 테스트를 제외했으므로 비공개 원본 전체 테스트 범위와 동일하지 않습니다. 웹 서비스 배포는 소스 공개와 별도로 진행합니다.

## 빠른 시작

Linux/Unix 환경에서 Python 3.14, Node.js와 npm이 필요합니다. Windows는 WSL 등 Linux 환경을 사용합니다. 저장소 루트에서 실행합니다.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r web/requirements.txt
npm ci --prefix plugins/hermes_ext/fortune_oracle/scripts
.venv/bin/python web/preview.py
```

`http://127.0.0.1:8765`에서 임시 DB를 사용하는 미리보기를 엽니다. 종료하면 임시 데이터가 삭제됩니다. 공개 호스팅에는 사용하지 마세요. Node 의존성은 `package-lock.json`에서 복원하며 `node_modules`는 소스에 포함하지 않습니다.

- [설치·검증·배포 준비](docs/PUBLIC_SETUP.md)
- [웹 기능과 개인정보 경계](web/README.md)
- [제품·명령 계약](docs/FORTUNE_ORACLE_PRODUCT_SPEC.md)
- [비밀 설정과 공개 경계](docs/SECURITY.md)
- [제3자 자료 고지](THIRD_PARTY_NOTICES.md)

## 공개와 사용 권리

이 저장소의 이력은 허용 파일만 추린 **독립 최초 커밋**에서 시작합니다. 이전 비공개 저장소의 커밋·태그·Git 객체를 가져오거나 병합하지 않습니다. 변경을 올리기 전에는 [비밀 설정과 공개 경계](docs/SECURITY.md)의 커밋 검사를 실행합니다.

프로젝트 전체에 적용할 루트 라이선스는 권리자의 결정 전까지 부여하지 않았습니다. 소스를 볼 수 있다는 사실만으로 재배포·상업적 사용 허가가 생기지는 않습니다. 포함된 제3자 고지와 라이선스는 유지합니다. 선택적 베딕 의존성의 라이선스 적용 방식과 상용 이용은 미해결이며, 코드 공개·공개 서비스 활성화·상품 판매는 각각 검토할 범위입니다. [설치 안내의 의존성 범위](docs/PUBLIC_SETUP.md)를 확인하세요.
