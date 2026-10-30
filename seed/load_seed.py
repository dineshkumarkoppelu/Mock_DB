"""Generate the synthetic CRM dataset and load it into the dockerised Postgres - only if empty.

    python seed/load_seed.py             # generate + load (aborts if any table has rows)
    python seed/load_seed.py --dry-run   # generate and print row counts only

Needs `pip install faker`, Docker running, and the stack up (`docker compose up -d`).
Loads inside a single transaction, via `psql` in the db container.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.seed.generator import generate  # noqa: E402

SEED = 42
LOOKBACK_MONTHS = 12
CAPACITY = 12
BATCH = 500

TABLES = {  # table -> columns, in FK-safe load order
    "sales_people": ["id", "name", "email", "region", "joined_on", "active", "capacity"],
    "clients": ["id", "name", "industry", "size", "region", "created_on"],
    "deals": [
        "id", "title", "value", "status", "stage", "created_at", "qualified_at", "proposal_at",
        "negotiation_at", "expected_close_date", "closed_at", "domain", "client_id", "owner_id",
    ],
    "activities": ["id", "type", "date", "outcome", "deal_id", "sales_person_id"],
}


def literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    return "'" + str(v).replace("'", "''") + "'"


def build_sql(dataset) -> str:
    out = [
        "DO $$ BEGIN",
        "  IF EXISTS (SELECT 1 FROM sales_people) OR EXISTS (SELECT 1 FROM clients)",
        "     OR EXISTS (SELECT 1 FROM deals) OR EXISTS (SELECT 1 FROM activities) THEN",
        "    RAISE EXCEPTION 'Tables are not empty - refusing to seed';",
        "  END IF;",
        "END $$;",
    ]
    for table, cols in TABLES.items():
        rows = getattr(dataset, table)
        for i in range(0, len(rows), BATCH):
            values = ",\n".join(
                "(" + ", ".join(literal(r[c]) for c in cols) + ")" for r in rows[i : i + BATCH]
            )
            out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values};")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dataset = generate(
        seed=SEED, today=date.today(), lookback_months=LOOKBACK_MONTHS, capacity=CAPACITY
    )
    for table in TABLES:
        print(f"{table}: {len(getattr(dataset, table))} rows")
    if args.dry_run:
        return

    # PGAPPNAME=crm-app makes the notify trigger skip this bulk load (no event flood).
    cmd = [
        "docker", "compose", "exec", "-T", "-e", "PGAPPNAME=crm-app", "db",
        "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 --single-transaction',
    ]
    result = subprocess.run(
        cmd, input=build_sql(dataset), text=True, cwd=ROOT.parent, capture_output=True
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        sys.exit(f"Load failed (nothing was inserted):\n{result.stderr.strip()}")
    print("Seeded.")


if __name__ == "__main__":
    main()
