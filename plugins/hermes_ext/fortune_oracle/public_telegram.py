"""Bounded Fortune-only ingress through Hermes' native Telegram extension API.

This does not grant gateway/agent access. Only explicitly listed, local
Fortune commands run for a human in the default bot's private chat.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import re
import stat
import tempfile

logger = logging.getLogger(__name__)

# Deliberately explicit: registering another plugin command never publishes it.
PUBLIC_COMMANDS = frozenset({
    "fortune-help", "도움말", "register-birth", "사주등록", "show-profile", "사주확인",
    "profile-status", "delete-profile", "사주삭제", "today-fortune", "오늘운세",
    "tomorrow-fortune", "내일운세", "week-fortune", "이번주운세", "month-kline", "월간운세",
    "life-kline", "인생k선", "year-kline", "kline-card", "bazi-trace", "팔자강약",
    "daily-on", "daily-off", "set-location", "clear-location", "oracle", "fortune-full",
    "종합운세", "oracle-short", "짧은운세", "astro", "western", "vedic", "qimen", "기문",
    "tarot", "타로", "iching", "주역",
})
_CLOSED_COMMANDS = frozenset({
    "deep-fortune", "심층운세", "ziwei-deep", "compatibility", "궁합", "voice-fortune", "운세음성",
})
PUBLIC_HELP = """Fortune Oracle

출생정보를 한 번에 등록하면 풀이를 받을 수 있습니다.
/register_birth 1990년 5월 17일 오후 12시 30분, 가상가, 남성
출생시각은 생략할 수 있으며 모르는 시주·대운은 계산하지 않습니다.
/show_profile · /profile_status · /delete_profile 확인
한국어: /사주등록 · /사주확인 · /사주삭제 확인

/today_fortune · /tomorrow_fortune · /week_fortune
/month_kline · /life_kline · /kline_card · /kline_card year
/bazi_trace — 오행 강약의 경험적 참고
/oracle · /western · /vedic — Vedic은 참고용 근사
/qimen 질문 — KST 질문 시각 판
/tarot 질문 · /iching 질문
/set_location 도시 | IANA_ZONE [| 위도 | 경도] · /clear_location

/daily_on [HH:MM] · /daily_off
직접 동의한 경우 다음 날부터 KST 아침(06:00–11:59)에 하루 최대 한 번 보냅니다.
등록 정보와 수신 설정은 /delete_profile 확인 으로 함께 삭제할 수 있습니다.
계산하지 못한 응답은 '계산 결과가 아님'으로 표시합니다.
심층 풀이·궁합·음성은 공개 대화에서 아직 제공하지 않습니다.
오락과 자기성찰용이며 의학, 투자, 법률 결정을 지시하지 않습니다."""

_FAILURE = "요청을 처리하지 못했습니다. 잠시 후 같은 명령을 다시 보내 주세요."
_CARD_FAILURE = "K선 이미지를 보내지 못했습니다. /month_kline 으로 확인하거나 /kline_card 를 다시 시도해 주세요."
_BUSY = "앞선 요청을 처리 중입니다. 잠시 후 다시 보내 주세요."
_ENTRY_GUIDE = """운세 명령을 확인해 주세요.
처음이라면 출생정보를 다음처럼 한 줄로 등록해 주세요.
/register_birth 1990년 5월 17일 오후 12시 30분, 가상가, 남성
출생시각은 모르면 생략할 수 있습니다. 나누어 보낸 정보는 등록하지 않습니다.
이미 등록했다면 /today_fortune · 조회 /show_profile
전체 안내: /fortune_help"""
# Withdrawal/deletion retain bounded capacity even when other users are calculating.
# A user's own requests remain serialized, including an abandoned worker finishing later.
_CONTROL_COMMANDS = frozenset({"daily-off", "delete-profile", "사주삭제"})
# Rewiring an application or replacing its adapter must not forget running workers.
# Admission and done callbacks run on the gateway event loop; threads never mutate this set.
_ACTIVE_USERS = set()
_ACTIVE_CALCULATIONS = set()
_ACTIVE_CONTROLS = set()


def enabled():
    return os.environ.get("FORTUNE_PUBLIC_TELEGRAM", "").strip() == "1"


def _command(text, bot_username):
    if not isinstance(text, str):
        return None
    parts = text.lstrip().split(maxsplit=1)
    if not parts or not parts[0].startswith("/"):
        return "_entry-guide", ""
    token = parts[0][1:]
    if "@" in token:
        token, suffix = token.split("@", 1)
        if not bot_username or suffix.lower() != bot_username.lower():
            return None
    name = token.lower().replace("_", "-")
    if name in {"start", "help"}:
        name = "fortune-help"
    if name not in PUBLIC_COMMANDS | _CLOSED_COMMANDS:
        return "_entry-guide", ""
    return name, parts[1].strip() if len(parts) == 2 else ""


def _private_identity(message):
    chat, user = getattr(message, "chat", None), getattr(message, "from_user", None)
    if (getattr(chat, "type", None) != "private" or not user
            or getattr(user, "is_bot", True) is not False
            or getattr(message, "sender_chat", None)
            or getattr(message, "business_connection_id", None)):
        return None
    uid, cid = str(getattr(user, "id", "")), str(getattr(chat, "id", ""))
    mid = str(getattr(message, "message_id", ""))
    if not all(re.fullmatch(r"[1-9][0-9]{0,19}", s) for s in (uid, cid, mid)) or uid != cid:
        return None
    return uid, cid, mid


def _card_file(text):
    first, separator, caption = text.partition("\n")
    if not separator or not first.startswith("MEDIA:"):
        raise ValueError("missing generated card")
    path = Path(first[6:])
    if (not path.is_absolute() or path.parent != Path(tempfile.gettempdir())
            or not re.fullmatch(r"fortune_kline_[A-Za-z0-9_-]+\.png", path.name)):
        raise ValueError("unexpected card path")
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
            or not 0 < info.st_size <= 3 * 1024 * 1024):
        raise ValueError("invalid card file")
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("invalid card signature")
    return path, caption


async def _send(adapter, cid, mid, text, thread_id=None):
    metadata = {"thread_id": thread_id} if thread_id else None
    receipt = await adapter.send(cid, text, reply_to=mid, metadata=metadata)
    if getattr(receipt, "success", False) is not True:
        raise RuntimeError("text delivery failed")


def _invoke_bound(handler, args, uid, cid):
    from gateway.session_context import get_session_env
    if (get_session_env("HERMES_SESSION_PLATFORM") != "telegram"
            or get_session_env("HERMES_SESSION_USER_ID") != uid
            or get_session_env("HERMES_SESSION_CHAT_ID") != cid):
        raise RuntimeError("public request identity not bound")
    return handler(args)


def make_factory(handlers):
    """Capture only Fortune-owned callables; never consult a global command registry."""
    published = {name: handlers[name] for name in PUBLIC_COMMANDS if name in handlers}

    def factory(application, adapter):
        # Optional SDK stays out of ordinary CLI/tests and plugin import.
        from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

        if not enabled() or getattr(adapter, "_owner_profile", None) not in (None, "default"):
            return
        for previous in list(application.handlers.get(-1, [])):
            if getattr(previous.callback, "_fortune_public_handler", False):
                application.remove_handler(previous, group=-1)
        active = _ACTIVE_USERS

        def candidate(message):
            if not enabled() or message is None:
                return None
            identity = _private_identity(message)
            if identity is None:
                return None
            try:
                username = getattr(application.bot, "username", None)
                command = _command(getattr(message, "text", None), username)
            except Exception:
                return None
            if command is None:
                return None
            uid, cid, mid = identity
            runner = getattr(adapter, "gateway_runner", None)
            if runner is None:
                runner = getattr(getattr(adapter, "_message_handler", None), "__self__", None)
            if runner is None:
                return None
            try:
                source = adapter.build_source(
                    chat_id=cid, chat_type="dm", user_id=uid, is_bot=False, message_id=mid,
                    thread_id=str(message.message_thread_id) if getattr(message, "is_topic_message", False) else None,
                )
                adapter._canonicalize(source)
                if (getattr(source, "profile_route_rejected", False)
                        or getattr(source, "profile", None) not in (None, "default")
                        or runner._delivery_adapter_for(source) is not adapter):
                    return None
                authorized = runner._is_user_authorized_for_source(source)
                if authorized is not False:  # Authorized users keep the normal gateway path.
                    return None
            except Exception:
                logger.warning("fortune-oracle: public ingress identity unavailable")
                return None
            return identity, command, runner, source

        class PublicFilter(filters.MessageFilter):
            def filter(self, message):
                # Filter before PTB's accepted-update latch; preserve the owner's
                # original ingress and retry behavior for all non-public messages.
                return candidate(message) is not None

        async def callback(update, context):
            message = getattr(update, "message", None)
            selected = candidate(message)
            if selected is None:
                return
            (uid, cid, mid), command, runner, source = selected

            # From here, consume even on errors. Never fall through into agent/pairing.
            task = None
            acquired = False
            bucket = None
            try:
                name, args = command
                if len(message.text) > 2048:
                    text = "입력이 너무 깁니다. 2,048자 이내로 한 줄에 입력해 주세요. /fortune_help"
                elif name == "_entry-guide":
                    # Never register bare birth data or pass unknown text to agent/pairing.
                    text = _ENTRY_GUIDE
                elif name in _CLOSED_COMMANDS:
                    text = "이 기능은 공개 대화에서 아직 제공하지 않습니다. 계산된 풀이와 이용 안내: /oracle · /fortune_help"
                elif name in ("fortune-help", "도움말"):
                    text = PUBLIC_HELP
                else:
                    bucket = _ACTIVE_CONTROLS if name in _CONTROL_COMMANDS else _ACTIVE_CALCULATIONS
                    limit = 2 if name in _CONTROL_COMMANDS else 4
                    if uid in active or len(bucket) >= limit:
                        await _send(adapter, cid, mid, _BUSY, source.thread_id)
                        raise ApplicationHandlerStop
                    active.add(uid)
                    bucket.add(uid)
                    acquired = True
                    from gateway.session import build_session_context
                    session = build_session_context(source, runner.config)
                    session.session_key = runner._session_key_for_source(source)
                    with runner._session_env_scope(session):
                        task = asyncio.create_task(runner._run_in_executor_with_context(
                            _invoke_bound, published[name], args, uid, cid))
                        text = await asyncio.shield(task)
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty public response")
                if name == "kline-card" and text.startswith("MEDIA:"):
                    path, caption = _card_file(text)
                    try:
                        receipt = await adapter.send_image_file(
                            cid, str(path), caption=caption[:900], reply_to=mid,
                            metadata={"thread_id": source.thread_id} if source.thread_id else None,
                        )
                        if getattr(receipt, "success", False) is not True:
                            raise RuntimeError("card delivery failed")
                    finally:
                        path.unlink(missing_ok=True)
                else:
                    # User-authored MEDIA strings in names/questions remain ordinary text.
                    await _send(adapter, cid, mid, text, source.thread_id)
            except ApplicationHandlerStop:
                raise
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("fortune-oracle: public command failed")
                try:
                    await _send(adapter, cid, mid, _CARD_FAILURE if command[0] == "kline-card" else _FAILURE, source.thread_id)
                except Exception:
                    logger.warning("fortune-oracle: public reply unavailable")
            finally:
                if acquired:
                    if task is not None and not task.done():
                        # Cancellation doesn't stop the worker. Keep its slot until it finishes.
                        def release(done, user=uid, name=command[0], occupied=bucket):
                            active.discard(user)
                            occupied.discard(user)
                            if not done.cancelled():
                                error = done.exception()
                                if error is None and name == "kline-card":
                                    try:
                                        abandoned, _ = _card_file(done.result())
                                        abandoned.unlink(missing_ok=True)
                                    except Exception:
                                        pass
                        task.add_done_callback(release)
                    else:
                        active.discard(uid)
                        bucket.discard(uid)
            raise ApplicationHandlerStop

        callback._fortune_public_handler = True
        # A separate group preserves core first-match routing for authorized users.
        gate = filters.UpdateType.MESSAGE & filters.TEXT & filters.ChatType.PRIVATE & PublicFilter()
        application.add_handler(MessageHandler(gate, callback, block=True), group=-1)

    return factory
