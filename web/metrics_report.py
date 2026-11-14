"""Read only daily aggregate counts. Never export profiles or browser identifiers."""
import argparse
import json
from pathlib import Path
import sqlite3


def read_counts(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT day, event, view, count FROM metric_counts ORDER BY day, event, view")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"timezone": "Asia/Seoul", "unit": "unique browser sessions per day/event/view",
                      "counts": read_counts(args.database)}, ensure_ascii=False, indent=2))
