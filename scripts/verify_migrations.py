"""Rehearse migrations on SQLite copies; never mutate the supplied source databases."""

import hashlib
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_UP

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = {
    "invoices_invoice": {
        "total": 2,
        "tax": 2,
        "paid_amount": 2,
        "to_pay": 2,
        "discount": 2,
    },
    "invoices_items": {"rate": 4, "calculated_rate": 4, "qty": 4, "price": 2},
    "invoices_payment": {"amount": 2},
    "invoices_openingbalance": {"amount": 2},
}


def snapshot(database):
    result = {}
    with closing(
        sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    ) as conn:
        for table, columns in COLUMNS.items():
            rows = conn.execute(
                f"SELECT id, {', '.join(columns)} FROM {table} ORDER BY id"
            ).fetchall()
            result[table] = [
                (
                    row[0],
                    *[
                        None
                        if value is None
                        else Decimal(str(value)).quantize(
                            Decimal(10) ** -precision, rounding=ROUND_HALF_UP
                        )
                        for value, precision in zip(row[1:], columns.values())
                    ],
                )
                for row in rows
            ]
    return result


def main():
    for supplied in sys.argv[1:] or ["backup.sqlite3", "db2.sqlite3"]:
        source = (ROOT / supplied).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        before = snapshot(source)
        with tempfile.TemporaryDirectory(
            prefix=".migration-check-", dir=ROOT
        ) as folder:
            target = Path(folder) / "copy.sqlite3"
            assert target.resolve().is_relative_to(ROOT.resolve())
            with (
                closing(
                    sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
                ) as src,
                closing(sqlite3.connect(target)) as dst,
            ):
                src.backup(dst)
            env = dict(os.environ, DJANGO_DB_PATH=str(target))
            env.pop("POSTGRES_DB", None)
            run = subprocess.run(
                [sys.executable, str(ROOT / "manage.py"), "migrate", "--noinput"],
                env=env,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            if run.returncode:
                raise RuntimeError(run.stdout + run.stderr)
            if before != snapshot(target):
                raise AssertionError(
                    f"Rounded financial records changed for {source.name}"
                )
            with closing(sqlite3.connect(target)) as conn:
                posted = conn.execute(
                    "SELECT COUNT(*) FROM invoices_invoice WHERE is_posted=1"
                ).fetchone()[0]
                statuses = conn.execute(
                    "SELECT COUNT(*) FROM invoices_invoice WHERE status='posted'"
                ).fetchone()[0]
                if posted != statuses:
                    raise AssertionError("Posted-state backfill mismatch")
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise AssertionError(f"Foreign-key violations: {violations[:5]}")
            print(
                f"PASS {source.name}: "
                + ", ".join(
                    f"{table.removeprefix('invoices_')}={len(rows)}"
                    for table, rows in before.items()
                )
                + "; rounded amounts and posted states preserved"
            )
        if digest != hashlib.sha256(source.read_bytes()).hexdigest():
            raise AssertionError("Source database unexpectedly changed")


if __name__ == "__main__":
    main()
