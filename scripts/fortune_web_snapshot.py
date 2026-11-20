#!/usr/bin/env python3
"""Private SQLite snapshots and aggregate-only recovery into a new file."""
import argparse
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "web"), str(root / "plugins")]
from fortune_web.snapshots import PublicationUncertainError, backup, restore_aggregates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore-aggregates"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True, help="New file in an existing owner-only directory outside this checkout")
    parser.add_argument("--timeout", type=float, default=10, help="SQLite work budget in seconds, at most 60; not an OS I/O interrupt")
    args = parser.parse_args()
    try:
        action = backup if args.operation == "backup" else restore_aggregates
        result = action(args.source, args.destination, timeout=args.timeout)
    except PublicationUncertainError:
        print(json.dumps({"ok": False, "error": "publication_uncertain",
                          "hint": "Check the destination privately before retrying; no existing source was replaced."}))
        return 1
    except Exception:
        # Paths, SQL errors and private values are deliberately absent from output.
        print(json.dumps({"ok": False, "error": "snapshot_failed",
                          "hint": "Check private file/directory permissions, supported schema, new destination and lock/time budget."}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
