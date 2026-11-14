#!/usr/bin/env python3
"""Fortune Oracle — Qimen Dunjia Bridge (Phase 35)

kinqimen 패키지를 optional dependency로 사용하여 기문둔갑 판을 계산한다.
import 실패, 계산 실패, 이상 입력은 모두 fail-open 텍스트 응답으로 처리한다.

금지:
- shell=True 사용 금지
- 외부 네트워크 호출 금지
- AI/LLM 호출 금지
- 파일 쓰기 금지

이 결과는 오락과 자기성찰 용도이며 의학, 투자, 법률 결정을 지시하지 않습니다.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from typing import Any, Dict, List, Optional

from .qimen_schema import (
    QimenChart,
    QimenPalace,
    QimenQuery,
    QimenResult,
)

logger = logging.getLogger(__name__)

# kinqimen 가용성 플래그 (모듈 로드 시 1회 결정)
_QIMEN_AVAILABLE: Optional[bool] = None
_QIMEN_IMPORT_ERROR: str = ""

# kinqimen.config module reference (cached after first successful import)
_QI_CONFIG_MODULE = None  # type: ignore[var-annotated]


@contextlib.contextmanager
def _scoped_kinqimen_config():
    """Scoped context-manager: kinqimen.config를 sys.modules['config']에 주입/복원.

    kinqimen.kinqimen은 내부적으로 ``import config``를 사용한다. 이 모듈은
    kinqimen.config를 의미하지만 Python import 체계상 다른 프로젝트의 config를
    참조할 수 있다. 이 context-manager는 호출 진입 시 sys.modules['config']에
    kinqimen.config를 주입하고, 호출 완료 후 원상복원한다.

    Usage:
        with _scoped_kinqimen_config():
            from kinqimen.kinqimen import Qimen
            q = Qimen(2026, 5, 28, 12, 30)
            raw = q.pan(1)
    """
    global _QI_CONFIG_MODULE
    if _QI_CONFIG_MODULE is None:
        try:
            import kinqimen.config as _qi_cfg
            _QI_CONFIG_MODULE = _qi_cfg
        except ImportError as e:
            logger.warning("qimen bridge: kinqimen.config import failed: %s", e)
            # Cannot scope — yield anyway; caller will handle ImportError
            yield
            return

    previous = sys.modules.get("config")
    sys.modules["config"] = _QI_CONFIG_MODULE
    try:
        yield
    finally:
        if previous is not None:
            sys.modules["config"] = previous
        elif "config" in sys.modules:
            del sys.modules["config"]


def _ensure_kinqimen() -> bool:
    """kinqimen 가용성을 확인한다.

    kinqimen 패키지와 kinqimen.config 둘 다 import 가능한지 확인한다.
    sys.modules['config'] 주입은 _scoped_kinqimen_config()가 호출 시점에 처리한다.

    Returns:
        True: kinqimen 사용 가능
        False: 사용 불가
    """
    global _QIMEN_AVAILABLE, _QIMEN_IMPORT_ERROR

    if _QIMEN_AVAILABLE is not None:
        return _QIMEN_AVAILABLE

    try:
        import kinqimen  # noqa: F401
    except ImportError as e:
        _QIMEN_AVAILABLE = False
        _QIMEN_IMPORT_ERROR = f"kinqimen 패키지가 설치되어 있지 않습니다: {e}"
        logger.warning("qimen bridge: %s", _QIMEN_IMPORT_ERROR)
        return False
    except Exception as e:
        _QIMEN_AVAILABLE = False
        _QIMEN_IMPORT_ERROR = f"kinqimen import 오류: {e}"
        logger.warning("qimen bridge: %s", _QIMEN_IMPORT_ERROR)
        return False

    # kinqimen.config도 import 가능한지 확인 (scoped 주입을 위한 pre-check)
    try:
        import kinqimen.config as _qi_cfg  # noqa: F401
        global _QI_CONFIG_MODULE
        _QI_CONFIG_MODULE = _qi_cfg
    except ImportError as e:
        _QIMEN_AVAILABLE = False
        _QIMEN_IMPORT_ERROR = f"kinqimen.config import 오류: {e}"
        logger.warning("qimen bridge: %s", _QIMEN_IMPORT_ERROR)
        return False
    except Exception as e:
        _QIMEN_AVAILABLE = False
        _QIMEN_IMPORT_ERROR = f"kinqimen config setup 오류: {e}"
        logger.warning("qimen bridge: %s", _QIMEN_IMPORT_ERROR)
        return False

    _QIMEN_AVAILABLE = True
    return True


def _resolve_option(method: str) -> int:
    """판식명을 kinqimen option 정수로 변환.

    Args:
        method: "拆補" 또는 "置閏" 또는 영어 "chaibu"/"zhirun"

    Returns:
        1 (拆補) 또는 2 (置閏)
    """
    if method in ("拆補", "chaibu", "1"):
        return 1
    if method in ("置閏", "zhirun", "2"):
        return 2
    return 1  # 기본 拆補


def _parse_zhifu_n_zhishi(zfzs: Dict[str, Any]) -> Dict[str, str]:
    """值符值使 dict를 단순화."""
    result: Dict[str, str] = {}
    try:
        zfs = zfzs.get("值符星宮", [])
        if isinstance(zfs, list) and len(zfs) >= 2:
            result["zhi_fu_star"] = str(zfs[0])
            result["zhi_fu_palace"] = str(zfs[1])

        zfd = zfzs.get("值符天干", [])
        if isinstance(zfd, list) and len(zfd) >= 2:
            result["zhi_fu_stem"] = str(zfd[1])

        zsm = zfzs.get("值使門宮", [])
        if isinstance(zsm, list) and len(zsm) >= 2:
            result["zhi_shi_door"] = str(zsm[0])
            result["zhi_shi_palace"] = str(zsm[1])
    except Exception:
        pass
    return result


def _parse_xun_kong(xun_kong: Any) -> str:
    """旬空 파싱."""
    if isinstance(xun_kong, dict):
        parts: List[str] = []
        for key, val in xun_kong.items():
            parts.append(f"{key}:{val}")
        return " ".join(parts)
    return str(xun_kong)


def _parse_horse_star(hs: Any) -> Dict[str, str]:
    """馬星 파싱."""
    result: Dict[str, str] = {}
    if isinstance(hs, dict):
        for key, val in hs.items():
            result[str(key)] = str(val)
    return result


def _build_palaces(
    pan_sky: Dict[str, str],
    pan_earth: Dict[str, str],
    doors: Dict[str, str],
    stars: Dict[str, str],
    gods: Dict[str, str],
    chang_sheng: Dict[str, Any],
) -> Dict[str, QimenPalace]:
    """천판/지판/문/성/신/장생운을 QimenPalace dict로 변환."""
    result: Dict[str, QimenPalace] = {}

    # 모든 궁위 키 수집
    all_keys: set = set(pan_sky.keys()) | set(pan_earth.keys()) | set(doors.keys())

    for palace_name in all_keys:
        # 천판: pan_sky는 tuple 반환 가능 (두 판일 때)
        sky_val = pan_sky.get(palace_name, "")
        if isinstance(sky_val, tuple):
            sky_val = sky_val[0]

        # 장생운(천판 기준)
        life_phase = ""
        try:
            cs_tian = chang_sheng.get("天盤", {})
            palace_cs = cs_tian.get(palace_name, {})
            if isinstance(palace_cs, dict):
                for stem, phase in palace_cs.items():
                    life_phase = str(phase)
                    break
        except Exception:
            pass

        result[palace_name] = QimenPalace(
            palace_name=str(palace_name),
            sky_stem=str(sky_val),
            earth_stem=str(pan_earth.get(palace_name, "")),
            door=str(doors.get(palace_name, "")),
            star=str(stars.get(palace_name, "")),
            god=str(gods.get(palace_name, "")),
            life_phase=life_phase,
        )

    return result


def calculate_qimen(query: QimenQuery) -> QimenResult:
    """기문둔갑 계산 메인 함수. fail-open: 어떤 오류도 QimenResult로 래핑.

    Args:
        query: QimenQuery 인스턴스.

    Returns:
        QimenResult. ok=False면 error_code/message 확인.
    """
    # 1. 입력 검증
    err = query.validate()
    if err:
        logger.debug("QimenQuery validation failed: %s", err)
        return QimenResult.error("INVALID_INPUT", err)

    # 2. kinqimen 가용성 확인
    if not _ensure_kinqimen():
        return QimenResult.error("DEPENDENCY_MISSING", _QIMEN_IMPORT_ERROR)

    # 3. kinqimen 호출 (scoped config 주입)
    option = _resolve_option(query.method)
    try:
        with _scoped_kinqimen_config():
            from kinqimen.kinqimen import Qimen

            qimen = Qimen(query.year, query.month, query.day, query.hour, query.minute)
            raw = qimen.pan(option)
    except ImportError as e:
        logger.warning("qimen bridge ImportError: %s", e)
        return QimenResult.error("DEPENDENCY_MISSING", f"kinqimen 모듈 로드 실패: {e}")
    except Exception as e:
        logger.warning("qimen bridge calculation error: %s", e)
        return QimenResult.error("CALCULATION_ERROR", f"기문둔갑 계산 중 오류가 발생했습니다: {e}")

    # 4. 결과 파싱
    try:
        # 판식
        method_name = str(raw.get("排盤方式", "拆補"))

        # 간지
        ganzhi = str(raw.get("干支", ""))

        #旬首
        xun_shou = str(raw.get("旬首", ""))

        #旬空
        xun_kong = _parse_xun_kong(raw.get("旬空", {}))

        #局日
        ju_day = str(raw.get("局日", ""))

        #排局
        pai_ju = str(raw.get("排局", ""))

        #節氣
        jie_qi = str(raw.get("節氣", ""))

        #值符值使
        zfzs = _parse_zhifu_n_zhishi(raw.get("值符值使", {}))

        #天乙
        tian_yi = str(raw.get("天乙", ""))

        #馬星
        horse_star = _parse_horse_star(raw.get("馬星", {}))

        # 궁위 데이터
        pan_sky = raw.get("天盤", {})
        pan_earth = raw.get("地盤", {})
        doors = raw.get("門", {})
        stars = raw.get("星", {})
        gods = raw.get("神", {})
        chang_sheng = raw.get("長生運", {})

        # pan_sky가 tuple일 수 있음 (두 판 반환)
        if isinstance(pan_sky, tuple):
            pan_sky = pan_sky[0] if pan_sky[0] else pan_sky[1]

        palaces = _build_palaces(pan_sky, pan_earth, doors, stars, gods, chang_sheng)

        chart = QimenChart(
            method=method_name,
            ganzhi=ganzhi,
            xun_shou=xun_shou,
            xun_kong=xun_kong,
            ju_day=ju_day,
            pai_ju=pai_ju,
            jie_qi=jie_qi,
            zhi_fu_stem=zfzs.get("zhi_fu_stem", ""),
            zhi_fu_star=zfzs.get("zhi_fu_star", ""),
            zhi_shi_door=zfzs.get("zhi_shi_door", ""),
            tian_yi=tian_yi,
            horse_star=horse_star,
            palaces=palaces,
        )

        return QimenResult(ok=True, chart=chart, query=query)

    except Exception as e:
        logger.warning("qimen bridge result parsing error: %s", e)
        return QimenResult.error("PARSE_ERROR", f"기문둔갑 결과 파싱 중 오류: {e}")


def bridge_available() -> bool:
    """kinqimen 사용 가능 여부 확인."""
    return _ensure_kinqimen()
