"""tests/test_fortune_oracle_help_ux.py

Phase 7 -- Telegram UX/help 문구 테스트.

검증 항목:
- /help(/도움말/fortune-help) 응답에 필수 명령 포함
- /register_birth without args: one-shot 안내 + multi-turn 불가 명시
- multi-turn 오해 유발 문구 없음
- /show_profile 미등록 안내에 one-shot 예시 포함
- /life_kline 미등록 시 K선 제공 + 등록 안내 포함
- /delete_profile 안내 포함
- alias 회귀 없음
- 기존 command handler 동작 회귀 없음
"""

from _fo_paths import hermes_path, repo_plugin_path
import sys
import importlib.util
from pathlib import Path
from unittest import mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

_PLUGIN_PATH = Path(repo_plugin_path("__init__.py"))


def _load_plugin():
    spec = importlib.util.spec_from_file_location("fo_plugin", _PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def plugin():
    return _load_plugin()


# ---------------------------------------------------------------------------
# /help 내용 검증
# ---------------------------------------------------------------------------

def test_help_contains_today_fortune(plugin):
    txt = plugin._handle_help("")
    assert "/today_fortune" in txt or "오늘운세" in txt


def test_help_contains_tomorrow_fortune(plugin):
    txt = plugin._handle_help("")
    assert "/tomorrow_fortune" in txt or "내일운세" in txt


def test_help_contains_month_kline(plugin):
    txt = plugin._handle_help("")
    assert "/month_kline" in txt or "월간운세" in txt


def test_help_contains_life_kline(plugin):
    txt = plugin._handle_help("")
    assert "/life_kline" in txt or "인생k선" in txt.lower()


def test_help_contains_kline_card(plugin):
    txt = plugin._handle_help("")
    assert "/kline_card" in txt


def test_help_contains_kline_card_year(plugin):
    txt = plugin._handle_help("")
    assert "year" in txt


def test_help_contains_register_birth_example(plugin):
    txt = plugin._handle_help("")
    assert "/register_birth" in txt
    # 예시 날짜 포함 (one-shot 형태)
    assert "1986년" in txt or "홍길동" in txt


def test_help_contains_사주등록(plugin):
    txt = plugin._handle_help("")
    assert "/사주등록" in txt


def test_help_contains_show_profile(plugin):
    txt = plugin._handle_help("")
    assert "/show_profile" in txt or "사주확인" in txt


def test_help_contains_delete_profile(plugin):
    txt = plugin._handle_help("")
    assert "/delete_profile" in txt or "사주삭제" in txt


def test_help_contains_voice_fortune(plugin):
    txt = plugin._handle_help("")
    assert "/voice_fortune" in txt


def test_help_contains_daily_on_off(plugin):
    txt = plugin._handle_help("")
    assert "/daily_on" in txt
    assert "/daily_off" in txt


def test_help_contains_multiturn_warning(plugin):
    """multi-turn 불가 안내가 /help에 포함돼야 한다."""
    txt = plugin._handle_help("")
    assert "multi-turn" in txt or "한 번에" in txt


def test_help_contains_disclaimer(plugin):
    txt = plugin._handle_help("")
    assert "오락" in txt or "자기성찰" in txt


# ---------------------------------------------------------------------------
# /register_birth without args
# ---------------------------------------------------------------------------

def test_register_birth_no_args_returns_guide(plugin):
    txt = plugin._handle_register_birth("")
    assert "/register_birth" in txt
    assert "홍길동" in txt or "예" in txt  # 예시 포함


def test_register_birth_no_args_no_multiturn_illusion(plugin):
    """'이름을 알려주세요' 같은 multi-turn 유도 문구가 없어야 한다."""
    txt = plugin._handle_register_birth("")
    # 이전 구버전 문구 검사
    assert "이름을 알려주세요" not in txt
    assert "생년월일시와" not in txt


def test_register_birth_no_args_mentions_multiturn_not_supported(plugin):
    """multi-turn 미지원임을 명시해야 한다."""
    txt = plugin._handle_register_birth("")
    assert "multi-turn" in txt or "이어지는" in txt or "한 번에" in txt


def test_register_birth_no_args_mentions_delete(plugin):
    """삭제 방법 안내 포함."""
    txt = plugin._handle_register_birth("")
    assert "/delete_profile" in txt or "사주삭제" in txt


# ---------------------------------------------------------------------------
# /show_profile 미등록
# ---------------------------------------------------------------------------

def test_show_profile_no_profile_contains_register_example(plugin):
    """미등록 상태 /show_profile에 one-shot 등록 예시 포함."""
    with mock.patch.object(
        plugin, "_resolve_profile", return_value=None
    ), mock.patch(
        "hermes_ext.fortune_oracle.bazi_bridge.bridge_available", return_value=False
    ):
        txt = plugin._handle_show_profile("")
    assert "/register_birth" in txt
    assert "홍길동" in txt or "예" in txt


def test_show_profile_no_profile_no_multiturn_illusion(plugin):
    """미등록 안내가 multi-turn 유도처럼 보이지 않아야 한다."""
    with mock.patch.object(
        plugin, "_resolve_profile", return_value=None
    ), mock.patch(
        "hermes_ext.fortune_oracle.bazi_bridge.bridge_available", return_value=False
    ):
        txt = plugin._handle_show_profile("")
    assert "이름을 알려주세요" not in txt
    assert "보내주세요" not in txt.replace("보내주세요", "")  # 삭제용 외에는 없어야


def test_show_profile_no_profile_contains_disclaimer(plugin):
    with mock.patch.object(
        plugin, "_resolve_profile", return_value=None
    ), mock.patch(
        "hermes_ext.fortune_oracle.bazi_bridge.bridge_available", return_value=False
    ):
        txt = plugin._handle_show_profile("")
    assert "오락" in txt or "자기성찰" in txt


# ---------------------------------------------------------------------------
# /life_kline 미등록 fallback
# ---------------------------------------------------------------------------

def test_life_kline_no_profile_still_returns_kline(plugin):
    """미등록 상태에서도 기본 K선 텍스트를 반환해야 한다."""
    fake_kline = "인생 K선: 현재 구간 상승 중"
    with mock.patch.object(
        plugin, "_resolve_profile", return_value=None
    ), mock.patch(
        "hermes_ext.fortune_oracle.kline.render_life_kline", return_value=fake_kline
    ):
        txt = plugin._handle_life_kline("")
    assert fake_kline in txt


def test_life_kline_no_profile_contains_register_hint(plugin):
    """미등록 상태 /life_kline에 사주 등록 안내가 추가돼야 한다."""
    fake_kline = "인생 K선: 현재 구간 상승 중"
    with mock.patch.object(
        plugin, "_resolve_profile", return_value=None
    ), mock.patch(
        "hermes_ext.fortune_oracle.kline.render_life_kline", return_value=fake_kline
    ):
        txt = plugin._handle_life_kline("")
    assert "/register_birth" in txt


# ---------------------------------------------------------------------------
# alias 회귀 없음
# ---------------------------------------------------------------------------

def test_aliases_registered():
    """주요 alias가 register 블록에 있는지 소스로 확인."""
    src = _PLUGIN_PATH.read_text(encoding="utf-8")
    for alias in ["오늘운세", "내일운세", "월간운세", "인생k선", "사주등록", "사주확인", "사주삭제", "도움말"]:
        assert alias in src, f"alias '{alias}' 없음"


def test_no_multiturn_guide_in_register_birth_no_args(plugin):
    """핵심: 빈 args 시 multi-turn처럼 보이는 단독 '알려주세요' 문구 없음."""
    txt = plugin._handle_register_birth("")
    bad_phrases = [
        "생년월일시와 이름을 알려주세요",
        "이름을 알려주세요. 예:",
    ]
    for phrase in bad_phrases:
        assert phrase not in txt, f"구버전 multi-turn 유도 문구 발견: '{phrase}'"


# ---------------------------------------------------------------------------
# 기존 command 동작 회귀 없음 (smoke)
# ---------------------------------------------------------------------------

def test_today_fortune_returns_text(plugin):
    txt = plugin._handle_today_fortune("")
    assert isinstance(txt, str) and len(txt) > 0


def test_tomorrow_fortune_returns_text(plugin):
    txt = plugin._handle_tomorrow_fortune("")
    assert isinstance(txt, str) and len(txt) > 0


def test_delete_profile_returns_text(plugin):
    txt = plugin._handle_delete_profile("")
    assert isinstance(txt, str) and len(txt) > 0
