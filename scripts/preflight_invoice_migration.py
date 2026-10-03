"""Rehearse the InvoiceMaker Alembic upgrade on a private SQLite copy.

The source is opened read-only. The requested copy must not exist and its
parent directory must be private on POSIX. This script never changes or
deletes the source, nor does it delete the rehearsal copy.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]
VALID_STARTS = {
    "631e160e6364", "d72c913f1b08", "ea42d6a90b17",
    "f36b7c0912da", "c42f980d7b25", "b47a19de0c62",
}
TARGET = "b47a19de0c62"


class PreflightError(RuntimeError):
    pass


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def snapshot(connection: sqlite3.Connection) -> dict:
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise PreflightError("SQLite quick_check zlyhal.")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise PreflightError("Databáza obsahuje porušené cudzie kľúče.")
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    if "alembic_version" not in tables:
        raise PreflightError("Databáza nemá alembic_version; vyžaduje osobitnú legacy migráciu.")
    revisions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    if len(revisions) != 1 or revisions[0] not in VALID_STARTS:
        raise PreflightError("Neznáma alebo nejednoznačná Alembic revízia.")
    protected = {}
    for table in tables:
        if table == "alembic_version":
            continue
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({quoted(table)})")]
        digest = hashlib.sha256()
        count = 0
        selected = ", ".join(quoted(column) for column in columns)
        for row in connection.execute(f"SELECT {selected} FROM {quoted(table)} ORDER BY rowid"):
            digest.update(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
            digest.update(b"\n")
            count += 1
        protected[table] = {"columns": columns, "rows": count, "digest": digest.hexdigest()}
    return {"revision": revisions[0], "protected": protected}


def compare(source: dict, migrated: sqlite3.Connection) -> None:
    for table, old in source["protected"].items():
        current_columns = {row[1] for row in migrated.execute(
            f"PRAGMA table_info({quoted(table)})")}
        if not set(old["columns"]).issubset(current_columns):
            raise PreflightError(f"Po migrácii chýba pôvodný stĺpec v {table}.")
        selected = ", ".join(quoted(column) for column in old["columns"])
        digest = hashlib.sha256()
        count = 0
        for row in migrated.execute(f"SELECT {selected} FROM {quoted(table)} ORDER BY rowid"):
            digest.update(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
            digest.update(b"\n")
            count += 1
        if count != old["rows"] or digest.hexdigest() != old["digest"]:
            raise PreflightError(f"Migrácia zmenila pôvodné dáta v {table}.")


def rehearse(source: Path, copy: Path) -> dict:
    source = source.resolve(strict=True)
    parent = copy.parent.resolve(strict=True)
    copy = parent / copy.name
    if not source.is_file() or copy == source or copy.exists() or copy.is_symlink():
        raise PreflightError("Zadaj existujúci zdroj a novú odlišnú cestu kópie.")
    if os.name == "posix" and stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise PreflightError("Priečinok kópie musí mať súkromné oprávnenie 0700.")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        original.execute("PRAGMA query_only=ON")
        before = snapshot(original)
        descriptor = os.open(copy, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(copy)) as destination:
                original.backup(destination)
                destination.commit()
        except Exception:
            # The reserved copy is deliberately kept for inspection.
            raise

    # Direct CLI execution puts scripts/ (not the release root) on sys.path.
    # The rehearsal must also work from a clean Git archive on the VPS.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    # ai.py constructs its client at import time. No AI request is made by a
    # migration, so a non-secret placeholder keeps a clean release self-contained.
    os.environ.setdefault("OPENAI_API_KEY", "migration-rehearsal-only")

    from flask_migrate import upgrade
    from app import create_app
    from extensions import db

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "migration-rehearsal-only",
        "MAIL_SUPPRESS_SEND": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + copy.as_posix(),
    })
    with app.app_context():
        try:
            upgrade(directory=str(ROOT / "migrations"), revision=TARGET)
        finally:
            db.session.remove()
            db.engine.dispose()
    with closing(sqlite3.connect(copy.as_uri() + "?mode=ro", uri=True)) as migrated:
        migrated.execute("PRAGMA query_only=ON")
        after = snapshot(migrated)
        if after["revision"] != TARGET:
            raise PreflightError("Kópia nemá očakávanú koncovú revíziu.")
        compare(before, migrated)
    return {
        "source_revision": before["revision"],
        "copy_revision": after["revision"],
        "preserved_tables": len(before["protected"]),
        "preserved_rows": sum(item["rows"] for item in before["protected"].values()),
        "copy": str(copy),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--copy", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(rehearse(args.source, args.copy), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, PreflightError) as error:
        parser.exit(1, f"Skúška migrácie zlyhala: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
