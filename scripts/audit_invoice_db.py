"""Read-only schema and integrity inventory; never print customer rows."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def audit(database: Path) -> dict:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        check = connection.execute("PRAGMA quick_check").fetchone()[0]
        schema = connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = [name for kind, name, _ in schema if kind == "table"]
        counts = {name: connection.execute(f"SELECT COUNT(*) FROM {quoted(name)}").fetchone()[0]
                  for name in tables if name != "alembic_version"}
        version = (connection.execute("SELECT version_num FROM alembic_version").fetchone()
                   if "alembic_version" in tables else None)
        columns = {name: [row[1] for row in connection.execute(
            f"PRAGMA table_info({quoted(name)})")]
                   for name in tables}
        foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    return {
        "quick_check": check,
        "revision": version[0] if version else None,
        "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
        "tables": tables,
        "columns": columns,
        "row_counts": counts,
        "foreign_key_violations": foreign_key_violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.database), sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
