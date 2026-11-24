"""Synthetic Korean-calendar dates; independent KASI references in docs/web-lunar-calendar.md."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from fortune_web import service
from test_fortune_oracle_web import app, session, PROFILE


def test_legacy_profile_reads_as_solar(app):
    client = app.test_client()
    session(client)
    token = client.get_cookie("fortune_session").value
    assert app.extensions["fortune_store"].save(token, PROFILE)
    saved = client.get("/api/session").json["profile"]
    assert saved["birth_calendar"] == "solar"
    assert saved["birth_leap_month"] is False
    assert saved["birth_date_input"] == PROFILE["birth_date"]


def test_korean_lunar_leap_date_is_normalized_with_original_metadata():
    profile = service.validate_birth({"birth_date": "2023-02-01", "birth_calendar": "lunar",
                                      "birth_leap_month": True, "birth_time": "12:30",
                                      "timezone": "America/New_York"})
    assert profile["birth_date"] == "2023-03-22"
    assert profile["birth_date_input"] == "2023-02-01"
    assert profile["birth_calendar"] == "lunar"
    assert profile["birth_leap_month"] is True
    assert profile["birth_time"] == "12:30"
    assert profile["timezone"] == "America/New_York"


# KASI 2017 official almanac + 2023/2024 calendar tables, not library-generated expectations.
REFERENCES = [
    ("2017-05-01", False, "2017-05-26"),
    ("2017-05-01", True, "2017-06-24"),
    ("2017-06-01", False, "2017-07-23"),
    ("2017-12-01", False, "2018-01-17"),
    ("2023-01-01", False, "2023-01-22"),
    ("2023-02-01", False, "2023-02-20"),
    ("2023-02-30", False, "2023-03-21"),
    ("2023-02-01", True, "2023-03-22"),
    ("2023-02-29", True, "2023-04-19"),
    ("2023-12-01", False, "2024-01-11"),
    ("2023-12-30", False, "2024-02-09"),
    ("2024-01-01", False, "2024-02-10"),
    ("2024-12-01", False, "2024-12-31"),
]


@pytest.mark.parametrize("lunar,leap,solar", REFERENCES)
@pytest.mark.parametrize("zone", ["Asia/Seoul", "America/New_York"])
def test_independent_references_and_identical_real_calculation(lunar, leap, solar, zone):
    common = {"birth_time": "12:30", "timezone": zone, "gender": "female"}
    a = service.validate_birth({**common, "birth_date": lunar, "birth_calendar": "lunar", "birth_leap_month": leap})
    b = service.validate_birth({**common, "birth_date": solar})
    assert a["birth_date"] == solar
    assert a["birth_year"] == int(solar[:4])
    chart = service.chart(a)
    assert chart["computed"]
    assert chart == service.chart(b)
    from datetime import datetime, timezone
    now = datetime(2026, 10, 28, 1, tzinfo=timezone.utc)
    assert service.daily(a, "today", now) == service.daily(b, "today", now)
    assert service.reading_window(a, now) == service.reading_window(b, now)


@pytest.mark.parametrize("change", [
    {"birth_date": "2023-02-30", "birth_leap_month": True},
    {"birth_date": "2023-01-30"}, {"birth_date": "2024-02-01", "birth_leap_month": True},
    {"birth_date": "2017-06-01", "birth_leap_month": True},
    {"birth_date": "2023-13-01"}, {"birth_date": "2023-00-01"},
    {"birth_date": "2023-02-00"}, {"birth_date": "2023-02-31"},
    {"birth_date": "1899-12-01"}, {"birth_date": "2050-11-19"},
    {"birth_date": "2051-01-01"}, {"birth_date": "２０２３-02-01"},
    {"birth_leap_month": "false"}, {"birth_leap_month": 1}, {"birth_leap_month": None},
    {"birth_calendar": "chinese"}, {"birth_calendar": None},
    {"birth_calendar": "solar", "birth_leap_month": True},
    {"birth_date_input": "2023-01-01"},
])
def test_invalid_lunar_does_not_replace_saved_profile(app, change):
    client = app.test_client(); headers = session(client)
    assert client.put("/api/profile", headers=headers, json=PROFILE).status_code == 200
    before = client.get("/api/session").json["profile"]
    payload = {"birth_date": "2023-02-01", "birth_calendar": "lunar", **change}
    assert client.put("/api/profile", headers=headers, json=payload).status_code == 400
    assert client.get("/api/session").json["profile"] == before
    assert client.post("/api/compat", headers=headers, json={"partner": payload}).status_code == 400


def test_persistence_edit_and_partner_equivalence(app):
    client = app.test_client(); headers = session(client)
    payload = {**PROFILE, "birth_date": "2017-05-01", "birth_calendar": "lunar", "birth_leap_month": True}
    saved = client.put("/api/profile", headers=headers, json=payload).json["profile"]
    assert saved["birth_date"] == "2017-06-24"
    assert client.get("/api/session").json["profile"] == saved
    edit = {key: saved[key] for key in service.FIELDS | service.CALENDAR_FIELDS}
    edit.update(birth_date=saved["birth_date_input"], display_name="가상 수정")
    assert client.put("/api/profile", headers=headers, json=edit).json["profile"]["birth_date"] == "2017-06-24"
    lunar = {key: value for key, value in payload.items() if key != "display_name"}
    solar = {**lunar, "birth_date": "2017-06-24", "birth_calendar": "solar", "birth_leap_month": False}
    a = client.post("/api/compat", headers=headers, json={"partner": lunar})
    b = client.post("/api/compat", headers=headers, json={"partner": solar})
    assert a.status_code == b.status_code == 200 and a.json["computed"]
    assert a.json == b.json
    assert client.put("/api/profile", headers=headers, json=solar).json["profile"]["birth_date_input"] == "2017-06-24"


def test_converted_solar_day_drives_dst_validation():
    # KASI 2024 month 2 begins March 10: US spring DST gap.
    for calendar, day in [("lunar", "2024-02-01"), ("solar", "2024-03-10")]:
        with pytest.raises(service.InvalidProfile):
            service.validate_birth({"birth_calendar": calendar, "birth_date": day,
                                    "birth_time": "02:30", "timezone": "America/New_York"})


def test_lunar_upper_limit_is_not_silently_extended(monkeypatch):
    from datetime import date
    class FutureDate(date):
        @classmethod
        def today(cls):
            return cls(2051, 1, 1)
    monkeypatch.setattr(service, "date", FutureDate)
    p = service.validate_birth({"birth_calendar": "lunar", "birth_date": "2050-11-18"})
    assert p["birth_date"] == "2050-12-31"
    with pytest.raises(service.InvalidProfile):
        service.validate_birth({"birth_calendar": "lunar", "birth_date": "2050-11-19"})


def test_lunar_lower_limit_and_unknown_time():
    p = service.validate_birth({"birth_calendar": "lunar", "birth_date": "1900-01-01"})
    assert p["birth_date_input"] == "1900-01-01" and p["birth_time"] == ""
    assert service.chart(p)["computed"]

