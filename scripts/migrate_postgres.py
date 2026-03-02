"""Run PostgreSQL SQL migrations from db/migrations/postgres."""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("psycopg is required: pip install psycopg[binary]") from exc

    migration_dir = Path(__file__).resolve().parents[1] / "db" / "migrations" / "postgres"
    files = sorted(migration_dir.glob("*.sql"))
    if not files:
        raise SystemExit("No migration files found")

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            for file in files:
                cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (file.name,))
                if cur.fetchone():
                    continue

                sql = file.read_text(encoding="utf-8")
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (file.name,))
                print(f"Applied migration: {file.name}")

        conn.commit()


if __name__ == "__main__":
    main()
