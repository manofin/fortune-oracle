"""Small, first-party funnel: fixed labels only, never reading or profile fields."""
from datetime import datetime
from zoneinfo import ZoneInfo


READING_VIEWS = {"today", "tomorrow", "month", "dday", "compat", "integrated"}
SHARE_VIEWS = {"today", "tomorrow", "dday"}
PREMIUM_THEMES = {"relationships", "resources", "career", "study", "western", "ziwei"}
# v1 identifies the editorial sample and its unvalidated price hypothesis together.
PRODUCT_SAMPLES = {"self_manual_v1", "conversation_guide_v1", "four_perspectives_v1"}
PRODUCT_SAMPLE_EVENTS = {"product_sample_viewed", "product_sample_interest"}
CLIENT_EVENTS = {
    "form_started": {"entry"},
    # A fixed link marker, not a sender ID or proof of a social-network share.
    "shared_link_visit": {"card"},
    "reading_viewed": READING_VIEWS,
    # Theme interest only: no contact details or promise of a launch notification.
    "premium_interest": PREMIUM_THEMES,
    **{event: PRODUCT_SAMPLES for event in PRODUCT_SAMPLE_EVENTS},
    **{event: SHARE_VIEWS for event in (
        "share_card_opened", "share_requested", "share_handoff", "share_cancelled",
        "share_download_requested", "share_link_copied", "share_failed",
    )},
}


def parse_event(payload):
    if not isinstance(payload, dict) or set(payload) != {"event", "view"}:
        raise ValueError("Only event and view are accepted")
    event, view = payload["event"], payload["view"]
    if (not isinstance(event, str) or not isinstance(view, str)
            or view not in CLIENT_EVENTS.get(event, set())):
        raise ValueError("Unknown event/view pair")
    return event, view


def metric_day(now=None):
    """All aggregates use one reporting zone, independent of birth time zones."""
    return (now or datetime.now(ZoneInfo("Asia/Seoul"))).astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
