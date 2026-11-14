import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from hermes_ext.fortune_oracle import oracle
from hermes_ext.fortune_oracle.platforms import telegram


def test_telegram_alias_parser_accepts_korean_slash_and_plain_aliases():
    assert telegram.parse_command("/오늘운세") == {"command": "today_fortune", "args": "", "raw": "/오늘운세"}
    assert telegram.parse_command("오늘운세") == {"command": "today_fortune", "args": "", "raw": "오늘운세"}
    assert telegram.parse_command("/사주등록 1986-01-02 03:04 서울") == {
        "command": "register_birth",
        "args": "1986-01-02 03:04 서울",
        "raw": "/사주등록 1986-01-02 03:04 서울",
    }
    assert telegram.parse_command("/사주삭제")["command"] == "delete_profile"
    assert telegram.parse_command("/운세음성")["command"] == "voice_fortune"
    assert telegram.parse_command("/매일운세켜기 07:30") == {
        "command": "daily_on",
        "args": "07:30",
        "raw": "/매일운세켜기 07:30",
    }
    assert telegram.parse_command("/매일운세끄기")["command"] == "daily_off"
    assert telegram.parse_command("/deep_fortune")["command"] == "deep_fortune"
    assert telegram.parse_command("/심층운세")["command"] == "deep_fortune"


def test_telegram_canonical_commands_are_bot_registration_safe():
    expected = {
        "tarot",
        "iching",
        "compatibility",
        "ziwei_deep",
        "today_fortune",
        "tomorrow_fortune",
        "week_fortune",
        "register_birth",
        "show_profile",
        "delete_profile",
        "voice_fortune",
        "daily_on",
        "daily_off",
        "life_kline",
        "year_kline",
        "month_kline",
        "kline_card",
        "deep_fortune",
        "oracle_short",   # Phase 39
        "bazi_trace",     # Phase 36/40
        "help",
        "profile_status",
        "qimen",
    }
    assert set(telegram.bot_command_names()) == expected
    assert telegram.validate_canonical_bot_commands() is True
    assert telegram.parse_command("/today_fortune")["command"] == "today_fortune"
    assert telegram.parse_command("/daily_on 07:30")["args"] == "07:30"


def test_fortune_store_separates_line_and_telegram_platforms(tmp_path):
    store = oracle.FortuneStore(tmp_path / "fortune.json")
    store.save_profile("line", "same-user", {"birth_date": "1990-01-01", "display_name": "LINE"})
    store.save_profile("telegram", "same-user", {"birth_date": "1991-01-01", "display_name": "TG"})
    store.set_daily_push("line", "same-user", "07:00", target="line-target")
    store.set_daily_push("telegram", "same-user", "08:00", target="tg-target")

    assert store.get_profile("line", "same-user")["display_name"] == "LINE"
    assert store.get_profile("telegram", "same-user")["display_name"] == "TG"
    assert store.get_daily_push("line", "same-user")["target"] == "line-target"
    assert store.get_daily_push("telegram", "same-user")["target"] == "tg-target"


def test_delete_profile_removes_only_that_platform_profile_and_opt_in(tmp_path):
    store = oracle.FortuneStore(tmp_path / "fortune.json")
    store.save_profile("line", "same-user", {"birth_date": "1990-01-01"})
    store.save_profile("telegram", "same-user", {"birth_date": "1991-01-01"})
    store.set_daily_push("line", "same-user", "07:00", target="line-target")
    store.set_daily_push("telegram", "same-user", "08:00", target="tg-target")

    store.delete_profile("telegram", "same-user")

    assert store.get_profile("telegram", "same-user") is None
    assert store.get_daily_push("telegram", "same-user") is None
    assert store.get_profile("line", "same-user") is not None
    assert store.get_daily_push("line", "same-user") is not None


def test_group_chat_redacts_birth_fields_and_hanja():
    profile = {
        "birth_date": "1986-01-02",
        "birth_time": "03:04",
        "birth_place": "Seoul",
        "name_hanja": "洪吉童",
        "display_name": "홍길동",
    }
    redacted = oracle.profile_for_display(profile, source_type="group")
    assert redacted["birth_date"] == "[REDACTED]"
    assert redacted["birth_time"] == "[REDACTED]"
    assert redacted["birth_place"] == "[REDACTED]"
    assert redacted["name_hanja"] == "[REDACTED]"
    assert redacted["display_name"] == "홍길동"


def test_daily_push_collection_filters_opt_in_only_and_can_filter_platform(tmp_path):
    store = oracle.FortuneStore(tmp_path / "fortune.json")
    store.set_daily_push("line", "U1", "07:00", target="line-target")
    store.set_daily_push("telegram", "U2", "08:00", target="tg-target")
    data = store._load()
    data["daily_push"]["telegram:U3"] = {
        "platform": "telegram",
        "user_id": "U3",
        "time": "09:00",
        "target": "tg-muted",
        "opt_in": False,
    }
    store._save(data)

    all_targets = oracle.collect_daily_push_targets(store)
    assert {target["target"] for target in all_targets} == {"line-target", "tg-target"}
    assert oracle.collect_daily_push_targets(store, platform="telegram") == [
        {"platform": "telegram", "user_id": "U2", "time": "08:00", "target": "tg-target"}
    ]


def test_telegram_voice_fortune_falls_back_when_tts_unavailable():
    result = telegram.prepare_voice_fortune(text="오늘은 가볍게 움직이세요.", tts_available=False)
    assert result["ok"] is False
    assert result["text_fallback"] == "오늘은 가볍게 움직이세요."
    assert "TTS" in result["error"]
