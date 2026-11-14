#!/usr/bin/env python3
"""Installed entry point; dry-run unless both --send and explicit activation exist."""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for directory in [ROOT / 'lib', ROOT / 'vendor', ROOT.parent]:
    if directory.is_dir():
        sys.path.insert(0, str(directory))
os.environ['FORTUNE_DEEP_ANALYSIS'] = '0'
os.environ.setdefault('FORTUNE_EPHEMERIS_PATH', str(ROOT / 'ephemeris' / 'de440s.bsp'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--at', help='ISO timestamp for dry-run only; must include offset')
    parser.add_argument('--store', type=Path)
    args = parser.parse_args()
    if args.send and (args.at or os.environ.get('FORTUNE_DAILY_ENABLED') != '1'):
        parser.error('live send requires FORTUNE_DAILY_ENABLED=1 and the real clock')
    from hermes_ext.fortune_oracle.daily_delivery import run_delivery, telegram_sender
    from hermes_ext.fortune_oracle.store import FortuneStore
    home = Path(os.environ.get('HERMES_HOME', str(Path.home() / '.hermes')))
    path = args.store or Path(os.environ.get('FORTUNE_ORACLE_STORE', str(home / 'fortune_oracle' / 'store.json')))
    # Dry-run of an absent store must not create production directories/files.
    if not path.is_file():
        print(json.dumps({'mode': 'send' if args.send else 'dry-run', 'candidates': 0, 'sent': 0,
                          'would_send': 0, 'status': 'store_missing'}))
        return 0
    try:
        sender = telegram_sender(os.environ.get('TELEGRAM_BOT_TOKEN', '')) if args.send else None
        report = run_delivery(FortuneStore(path), send=args.send, sender=sender,
                              now=datetime.fromisoformat(args.at) if args.at else None)
        marker = ROOT / 'DEPLOYED_COMMIT'
        report['deployment_sha'] = marker.read_text().strip() if marker.is_file() else 'development'
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1 if any(d['status'] in {'render_failed', 'uncertain_no_retry'} for d in report['decisions']) else 0
    except Exception as exc:
        # No exception text/traceback: network exceptions can include credential URLs.
        print(json.dumps({'status': 'worker_failed', 'error_type': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
