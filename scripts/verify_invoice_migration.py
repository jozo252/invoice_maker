"""Compare a pre-upgrade SQLite backup with a migrated database, read-only.

Reports only revisions and row counts. Never prints customer records.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preflight_invoice_migration import (  # noqa: E402
    PreflightError, TARGET, VALID_STARTS, compare, snapshot,
)


def verify(before_path: Path, after_path: Path) -> dict:
    before_path = before_path.resolve(strict=True)
    after_path = after_path.resolve(strict=True)
    if before_path == after_path:
        raise PreflightError("Záloha a výsledná databáza musia byť odlišné súbory.")
    with closing(sqlite3.connect(before_path.as_uri() + "?mode=ro", uri=True)) as before_db:
        before_db.execute("PRAGMA query_only=ON")
        before = snapshot(before_db)
        if before["revision"] not in VALID_STARTS:
            raise PreflightError("Neznáma východisková revízia zálohy.")
        with closing(sqlite3.connect(after_path.as_uri() + "?mode=ro", uri=True)) as after_db:
            after_db.execute("PRAGMA query_only=ON")
            after = snapshot(after_db)
            if after["revision"] != TARGET:
                raise PreflightError("Výsledná databáza nemá cieľovú revíziu.")
            compare(before, after_db)
    return {
        "before_revision": before["revision"],
        "after_revision": after["revision"],
        "preserved_tables": len(before["protected"]),
        "preserved_rows": sum(item["rows"] for item in before["protected"].values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.before, args.after), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, PreflightError) as error:
        parser.exit(1, f"Kontrola migrácie zlyhala: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
