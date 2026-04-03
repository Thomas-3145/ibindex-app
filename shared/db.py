import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from shared.models import SnapshotRow

_SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url


def get_connection() -> psycopg.Connection:  # type: ignore[type-arg]
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def init_db() -> None:
    schema = _SCHEMA_PATH.read_text()
    with get_connection() as conn:
        conn.execute(schema)


def get_latest_snapshots() -> list[SnapshotRow]:
    sql = """
        SELECT
            s.ticker,
            p.product_name,
            s.price,
            s.previous_price,
            s.price_change,
            s.nav,
            s.nav_calculated,
            s.nav_rebate_premium,
            s.nav_calculated_rebate_premium,
            s.weight,
            s.market_cap_weight,
            s.scraped_at
        FROM snapshots s
        JOIN products p ON p.ticker = s.ticker
        WHERE s.scrape_run_id = (
            SELECT id FROM scrape_runs
            WHERE status = 'ok'
            ORDER BY scraped_at DESC
            LIMIT 1
        )
        ORDER BY s.ticker
    """
    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()

    return [SnapshotRow(**row) for row in rows]


def get_latest_scrape_time() -> str | None:
    sql = "SELECT scraped_at FROM scrape_runs WHERE status = 'ok' ORDER BY scraped_at DESC LIMIT 1"
    with get_connection() as conn:
        row = conn.execute(sql).fetchone()
    return str(row["scraped_at"]) if row else None
