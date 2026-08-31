import os
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from shared.models import HoldingRow, ShareClassRow, SnapshotRow

_SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url


def get_connection() -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def init_db() -> None:
    schema = _SCHEMA_PATH.read_text()
    with get_connection() as conn:
        conn.execute(schema)


def get_latest_run() -> tuple[int, datetime] | None:
    """Id and timestamp of the most recent successful scrape run.

    Snapshot and holdings reads take the run id as a parameter so one page
    render never mixes data from two runs (a scrape may commit in between).
    """
    sql = """
        SELECT id, scraped_at FROM scrape_runs
        WHERE status = 'ok'
        ORDER BY scraped_at DESC
        LIMIT 1
    """
    with get_connection() as conn:
        row = conn.execute(sql).fetchone()
    return (row["id"], row["scraped_at"]) if row else None


def get_snapshots(run_id: int) -> list[SnapshotRow]:
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
        WHERE s.scrape_run_id = %s
        ORDER BY s.ticker
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (run_id,)).fetchall()

    return [SnapshotRow(**row) for row in rows]


def get_holdings(run_id: int) -> list[HoldingRow]:
    sql = """
        SELECT
            owner_ticker,
            holding_ticker,
            holding_name,
            exchange,
            value,
            category,
            category_name,
            scraped_at
        FROM holdings
        WHERE scrape_run_id = %s
        ORDER BY owner_ticker, value DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (run_id,)).fetchall()

    return [HoldingRow(**row) for row in rows]


def get_share_classes(run_id: int) -> list[ShareClassRow]:
    sql = """
        SELECT base_ticker, ticker, price, avg_volume, scraped_at
        FROM share_classes
        WHERE scrape_run_id = %s
        ORDER BY base_ticker, price
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, (run_id,)).fetchall()
    except psycopg.errors.UndefinedTable:
        # ArgoCD rolls out the app as soon as the image tag moves, but the
        # schema is applied by the scraper CronJob — which may be a day away.
        # The share class view degrades to hidden; failing here would take the
        # whole app down until the next scrape.
        return []

    return [ShareClassRow(**row) for row in rows]
