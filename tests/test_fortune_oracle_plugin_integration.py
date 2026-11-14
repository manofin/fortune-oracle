"""tests/test_fortune_oracle_plugin_integration.py

Phase 3~5 Telegram live integration — plugin handler 단위 테스트.
gateway/run.py, platforms/* 미수정 전제. plugin __init__.py handler만 테스트.
"""

from _fo_paths import hermes_path, repo_path, repo_plugin_path
import sys
import json
import importlib.util
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

_PLUGIN_PATH = Path(repo_plugin_path("__init__.py"))


def _load_plugin():
    spec = importlib.util.spec_from_file_location("fo_plugin", str(_PLUGIN_PATH))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def plugin():
    return _load_plugin()


@pytest.fixture(autouse=True)
def _no_implicit_user(monkeypatch):
    monkeypatch.delenv("FORTUNE_ORACLE_USER", raising=False)
    monkeypatch.delenv("FORTUNE_ORACLE_PROFILE", raising=False)


# ---------------------------------------------------------------------------
# 미등록 상태 (빈 store)
# ---------------------------------------------------------------------------

def _empty_store_load():
    return {"profiles": {}, "daily_push": {}}


def test_show_profile_no_profile_returns_safe_message(plugin):
    """profile 미등록 시 안전한 안내 메시지 반환."""
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_empty_store_load(),
    ):
        result = plugin._handle_show_profile("")
    assert "등록된 사주 정보가 없습니다" in result
    assert "/register_birth" in result
    assert "팔자:" not in result


def test_life_kline_no_profile_returns_kline_only(plugin):
    """profile 미등록 시 K선 텍스트 + 등록 힌트 반환 (팔자 bazi append는 없음).

    Phase 7 변경: 미등록 시에도 등록 안내 힌트가 추가된다.
    '팔자 기질 참고' 섹션(bazi 계산 결과)은 없어야 하지만
    '팔자 기질 참고 섹션' 문자열은 안내 힌트 안에 포함될 수 있다.
    """
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_empty_store_load(),
    ):
        result = plugin._handle_life_kline("")
    assert "K선" in result or "인생" in result or "2026" in result
    # bazi 계산 결과 섹션("🔮 팔자 기질 참고\n")은 없어야 함
    assert "\n🔮 팔자 기질 참고\n" not in result
    # 등록 힌트는 있어야 함 (Phase 7 추가)
    assert "/register_birth" in result


# ---------------------------------------------------------------------------
# 등록된 profile 상태
# ---------------------------------------------------------------------------

_SAMPLE_PROFILE = {
    "display_name": "테스트",
    "birth_date": "1990-01-01",
    "birth_time": "08:30",
    "birth_place": "Seoul",
    "timezone": "Asia/Seoul",
    "gender": "unknown",
}

_SAMPLE_STORE = {
    "profiles": {
        "telegram:12345678": _SAMPLE_PROFILE,
    },
    "daily_push": {},
}


def test_show_profile_with_profile_returns_bazi_summary(plugin, monkeypatch):
    """profile 등록 시 bazi 요약이 응답에 포함된다."""
    monkeypatch.setenv("FORTUNE_ORACLE_USER", "telegram:12345678")
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_SAMPLE_STORE,
    ):
        result = plugin._handle_show_profile("")
    # 팔자 정보 포함 확인
    assert "테스트" in result
    assert "팔자" in result or "기질" in result
    # disclaimer 포함
    assert "오락" in result or "자기성찰" in result


def test_show_profile_with_profile_fallback_when_bazi_fails(plugin, monkeypatch):
    """bazi 계산 실패해도 show_profile은 응답을 반환한다."""
    monkeypatch.setenv("FORTUNE_ORACLE_USER", "telegram:12345678")
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_SAMPLE_STORE,
    ):
        with mock.patch(
            "hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile",
            side_effect=RuntimeError("bazi 강제 실패"),
        ):
            result = plugin._handle_show_profile("")
    # 예외 전파 없이 응답 반환
    assert isinstance(result, str)
    assert len(result) > 0
    assert "테스트" in result


def test_life_kline_with_profile_appends_bazi(plugin, monkeypatch):
    """profile 등록 시 /life_kline에 팔자 기질 요약이 append된다."""
    monkeypatch.setenv("FORTUNE_ORACLE_USER", "telegram:12345678")
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_SAMPLE_STORE,
    ):
        result = plugin._handle_life_kline("")
    assert "팔자 기질" in result
    assert "기본 기질" in result
    assert "오락과 자기성찰 용도" in result


def test_life_kline_bazi_fail_returns_base_text(plugin):
    """bazi 실패 시 /life_kline은 기존 K선 텍스트만 반환한다."""
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_SAMPLE_STORE,
    ):
        with mock.patch(
            "hermes_ext.fortune_oracle.bazi_bridge.calculate_bazi_from_profile",
            side_effect=RuntimeError("강제 실패"),
        ):
            result = plugin._handle_life_kline("")
    assert "K선" in result or "인생" in result or "2026" in result
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# 기존 명령 회귀
# ---------------------------------------------------------------------------

def test_kline_card_not_affected(plugin):
    """_handle_kline_card는 bazi 변경에 영향받지 않는다."""
    result = plugin._handle_kline_card("")
    # MEDIA: 태그 또는 fallback 메시지
    assert isinstance(result, str)
    assert len(result) > 0


def test_month_kline_not_affected(plugin):
    """_handle_month_kline은 bazi 변경에 영향받지 않는다."""
    result = plugin._handle_month_kline("")
    assert isinstance(result, str)
    assert len(result) > 0
    assert "K선" in result or "월" in result


def test_today_fortune_not_affected(plugin):
    """_handle_today_fortune은 bazi 변경에 영향받지 않는다."""
    result = plugin._handle_today_fortune("")
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# _resolve_profile: 대상 사용자를 명시해야 하며 저장된 프로필을 추측하지 않는다
# ---------------------------------------------------------------------------

def test_resolve_profile_without_identity_never_picks_stored_profile(plugin):
    """gateway 세션·명시 사용자·프로필 파일이 없으면 저장된 프로필이 있어도 None."""
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_SAMPLE_STORE,
    ):
        assert plugin._resolve_profile() is None
        result = plugin._handle_show_profile("")
    assert "사용자를 확인할 수 없어" in result
    assert "테스트" not in result


def test_resolve_profile_explicit_user(plugin, monkeypatch):
    monkeypatch.setenv("FORTUNE_ORACLE_USER", "telegram:12345678")
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_SAMPLE_STORE,
    ):
        profile = plugin._resolve_profile()
    assert profile is not None
    assert profile["birth_date"] == "1990-01-01"


def test_resolve_profile_explicit_user_without_profile(plugin, monkeypatch):
    """명시한 사용자의 프로필이 없으면 다른 사용자의 프로필로 대체하지 않는다."""
    monkeypatch.setenv("FORTUNE_ORACLE_USER", "telegram:99999999")
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_SAMPLE_STORE,
    ):
        assert plugin._resolve_profile() is None


def test_resolve_profile_from_profile_file(plugin, monkeypatch, tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(_SAMPLE_PROFILE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("FORTUNE_ORACLE_PROFILE", str(path))
    with mock.patch(
        "hermes_ext.fortune_oracle.store.FortuneStore._load",
        return_value=_empty_store_load(),
    ):
        profile = plugin._resolve_profile()
    assert profile is not None and profile["display_name"] == "테스트"


def test_writes_require_identity(plugin, tmp_path, monkeypatch):
    """대상 사용자가 없으면 등록·삭제·알림·위치 저장을 하지 않는다."""
    store_path = tmp_path / "store.json"
    monkeypatch.setattr(plugin, "_STORE_PATH", store_path)
    for handler, args in [
        (plugin._handle_register_birth, "1990년 1월 1일 오전 8시 30분, 테스트"),
        (plugin._handle_delete_profile, "확인"),
        (plugin._handle_daily_on, "08:00"),
        (plugin._handle_daily_off, ""),
        (plugin._handle_set_location, "Seoul, Korea | Asia/Seoul"),
        (plugin._handle_clear_location, ""),
    ]:
        assert "사용자를 확인할 수 없어" in handler(args)
    assert not store_path.exists()


# ---------------------------------------------------------------------------
# Static: 금지 파일 수정 없음
# ---------------------------------------------------------------------------

def test_gateway_files_not_modified():
    """gateway/run.py, platforms/* 미수정 검증."""
    import subprocess
    gateway_repo = Path(hermes_path("hermes-agent"))
    if not gateway_repo.is_dir():
        pytest.skip("External Hermes checkout is not provisioned in the isolated HERMES_HOME")
    r = subprocess.run(
        ["git", "diff", "HEAD", "--name-only",
         "gateway/run.py", "gateway/platforms/"],
        cwd=gateway_repo,
        capture_output=True, text=True,
    )
    assert r.returncode == 0, "External Hermes checkout could not be inspected"
    # 변경된 파일 없어야 함
    changed = r.stdout.strip()
    assert changed == "", f"금지된 파일이 변경되었습니다: {changed}"
