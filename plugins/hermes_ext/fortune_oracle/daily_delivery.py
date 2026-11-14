"""Opt-in KST morning delivery. Default dry-run; no model calls or API retries.

Persist a claim BEFORE sending. A timeout/crash is ambiguous and consumes the
KST day's slot: avoiding duplicates takes priority over retrying lost messages.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Callable
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo

from .daily_reading import prepare_daily_reading
from .store import FortuneStore

KST = ZoneInfo('Asia/Seoul')


def _kst(now):
    value = now or datetime.now(KST)
    if value.tzinfo is None:
        raise ValueError('timezone-aware time required')
    return value.astimezone(KST)


def recipient_ref(key):
    return hashlib.sha256(key.encode()).hexdigest()


def candidates(data):
    """Only explicit Telegram opt-ins enter target enumeration."""
    return [(key, entry) for key, entry in sorted(data.get('daily_push', {}).items())
            if key.startswith('telegram:') and isinstance(entry, dict)
            and entry.get('opt_in') is True]


def reason_for(data, key, entry, now):
    uid = key.removeprefix('telegram:')
    if not re.fullmatch(r'[1-9][0-9]*', uid) or entry.get('target') != uid or entry.get('user_id') != uid:
        return 'invalid_private_target'
    if entry.get('platform') != 'telegram':
        return 'invalid_platform'
    try:
        consent = datetime.fromisoformat(entry['consented_at'])
        if consent.tzinfo is None or consent > now:
            return 'invalid_consent'
        start = datetime.fromisoformat(entry['start_date']).date()
        if start <= consent.astimezone(KST).date():
            return 'invalid_consent'
    except (KeyError, ValueError, TypeError):
        return 'renew_consent_required'
    if now.date() < start:
        return 'starts_tomorrow'
    profile = data.get('profiles', {}).get(key)
    if not isinstance(profile, dict) or not profile.get('birth_date'):
        return 'no_profile'
    record = data.get('daily_delivery', {}).get(recipient_ref(key), {})
    # Do not resend if a clock rollback goes to an already processed date.
    if record.get('date', '') >= now.date().isoformat():
        return 'already_attempted'
    hhmm = entry.get('time', '')
    if not isinstance(hhmm, str) or not re.fullmatch(r'(0[6-9]|1[01]):[0-5][0-9]', hhmm):
        return 'invalid_morning_time'
    if not 6 <= now.hour < 12 or now.strftime('%H:%M') < hhmm:
        return 'outside_window'
    return 'eligible'


def run_delivery(store: FortuneStore, *, send=False, sender: Callable | None = None,
                 now=None, renderer=prepare_daily_reading):
    """Return masked decisions only. Dry-run never changes consent/delivery data.

    Locks cover fresh consent/profile check, rendering, durable claim and bounded
    HTTP request. Thus /daily_off cannot return success before an in-flight send
    finishes, and no send can begin after the opt-out transaction completes.
    """
    if send and sender is None:
        raise ValueError('sender required for live delivery')
    at = _kst(now)
    report = {'mode': 'send' if send else 'dry-run', 'kst_date': at.date().isoformat(),
              'kst_time': at.isoformat(), 'candidates': 0, 'would_send': 0, 'sent': 0, 'decisions': []}
    with store.locked():
        initial = store._load()
        if send and 'daily_delivery' in initial:
            recent = {key: record for key, record in initial['daily_delivery'].items()
                      if record.get('date', '') >= at.date().isoformat()}
            if recent != initial['daily_delivery']:
                initial['daily_delivery'] = recent
                store._save(initial)
        keys = [key for key, _ in candidates(initial)]
    for key in keys:
        with store.locked():
            data = store._load()
            entry = data.get('daily_push', {}).get(key)
            if not entry or entry.get('opt_in') is not True:
                continue
            at = _kst(now)
            report['candidates'] += 1
            reason = reason_for(data, key, entry, at)
            decision = {'recipient': recipient_ref(key)[:12], 'status': reason}
            report['decisions'].append(decision)
            if reason != 'eligible':
                continue
            try:
                result = renderer(data['profiles'][key], day='today', reading_timezone='Asia/Seoul', now=at)
                text = result['text']
                if not isinstance(text, str) or not text.strip():
                    raise ValueError('empty reading')
                # Preserve the first-line calculation label, including failure responses.
                if result.get('computed') is not True and not text.startswith(('계산 결과가 아님', 'Not a calculated result')):
                    raise ValueError('unlabelled reading')
                text += '\n\n매일 운세 수신 동의로 보낸 메시지입니다. 해제: /daily_off'
                if len(text) > 4096:
                    raise ValueError('message too long')
            except Exception:
                decision['status'] = 'render_failed'
                continue
            if not send:
                report['would_send'] += 1
                decision['status'] = 'would_send'
                continue
            # A long rendering must not push a send past noon or onto another day.
            current = _kst(now)
            if current.date() != at.date() or reason_for(data, key, entry, current) != 'eligible':
                decision['status'] = 'window_expired'
                continue
            ledger = data.setdefault('daily_delivery', {})
            ref = recipient_ref(key)
            ledger[ref] = {'date': at.date().isoformat(), 'state': 'claimed', 'attempted_at': current.isoformat()}
            store._save(data)  # fsync + atomic replace, before any network call
            try:
                message_id = sender(entry['target'], text)
                if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
                    raise ValueError('missing receipt')
            except Exception:
                ledger[ref]['state'] = 'uncertain'
                decision['status'] = 'uncertain_no_retry'
            else:
                ledger[ref].update(state='sent', message_id=message_id)
                report['sent'] += 1
                decision['status'] = 'sent'
            store._save(data)
    return report


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def telegram_sender(token):
    """One HTTPS sendMessage request. Never log token, URL, body or exception."""
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token or ''):
        raise ValueError('Telegram credential unavailable')
    opener = build_opener(_NoRedirect)

    def send(target, text):
        payload = json.dumps({'chat_id': target, 'text': text}).encode('utf-8')
        request = Request(f'https://api.telegram.org/bot{token}/sendMessage', data=payload,
                          headers={'Content-Type': 'application/json'}, method='POST')
        with opener.open(request, timeout=15) as response:
            result = json.load(response)
        if result.get('ok') is not True:
            raise RuntimeError('delivery receipt unavailable')
        message = result.get('result', {})
        if str(message.get('chat', {}).get('id')) != target:
            raise RuntimeError('delivery target mismatch')
        return message.get('message_id')
    return send
