CREATE TABLE IF NOT EXISTS scrape_runs (
    id         SERIAL PRIMARY KEY,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status     TEXT NOT NULL CHECK (status IN ('ok', 'error'))
);

CREATE TABLE IF NOT EXISTS products (
    ticker          TEXT PRIMARY KEY,
    product_name    TEXT NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS snapshots (
    id                            SERIAL PRIMARY KEY,
    scrape_run_id                 INTEGER NOT NULL REFERENCES scrape_runs(id),
    ticker                        TEXT NOT NULL REFERENCES products(ticker),
    price                         NUMERIC NOT NULL,
    previous_price                NUMERIC,
    price_change                  NUMERIC,
    nav                           NUMERIC,
    nav_calculated                NUMERIC,
    nav_rebate_premium            NUMERIC,
    nav_calculated_rebate_premium NUMERIC,
    weight                        NUMERIC,
    market_cap_weight             NUMERIC,
    scraped_at                    TIMESTAMPTZ NOT NULL
);

-- Idempotent migration for existing databases
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS market_cap_weight NUMERIC;

CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_scraped
    ON snapshots(ticker, scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_snapshots_run
    ON snapshots(scrape_run_id);
