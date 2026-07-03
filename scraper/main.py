import sys
from datetime import datetime, timezone

import requests
import yfinance as yf  # type: ignore[import-untyped]

from shared.db import get_connection, init_db
from shared.models import ProductResponse, WeightResponse

PRODUCTS_URL = "https://ibindex.se/ibi/index/getProducts.req"
WEIGHTS_URL = "https://ibindex.se/ibi/index/getProductWeights.req"
TIMEOUT = 10


def to_yahoo_ticker(ibindex_ticker: str) -> str:
    return ibindex_ticker.replace(" ", "-") + ".ST"


def fetch_products() -> list[ProductResponse]:
    response = requests.get(PRODUCTS_URL, timeout=TIMEOUT)
    response.raise_for_status()
    return [ProductResponse.model_validate(item) for item in response.json()]


def fetch_weights() -> dict[str, float]:
    response = requests.get(WEIGHTS_URL, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if not data:
        return {}
    weights = [WeightResponse.model_validate(item) for item in data]
    return {w.ticker: w.weight for w in weights}


def fetch_market_cap_weights(products: list[ProductResponse]) -> dict[str, float]:
    market_caps: dict[str, float] = {}

    yahoo_tickers = [to_yahoo_ticker(p.ticker) for p in products]
    data = yf.Tickers(" ".join(yahoo_tickers))

    for p in products:
        yahoo_ticker = to_yahoo_ticker(p.ticker)
        try:
            info = data.tickers[yahoo_ticker].info
            shares = info.get("sharesOutstanding")
            if shares and p.price > 0:
                market_caps[p.ticker] = p.price * shares
        except Exception:
            pass

    total = sum(market_caps.values())
    if total == 0:
        return {}

    return {ticker: (cap / total) * 100 for ticker, cap in market_caps.items()}


def main() -> None:
    init_db()

    scraped_at = datetime.now(timezone.utc)

    try:
        products = fetch_products()
        weights = fetch_weights()

        print("Hämtar marknadsvärden från Yahoo Finance...")
        market_cap_weights = fetch_market_cap_weights(products)
        print(f"Marknadsvikt beräknad för {len(market_cap_weights)} bolag")

        with get_connection() as conn:
            row = conn.execute(
                "INSERT INTO scrape_runs (scraped_at, status) VALUES (%s, %s) RETURNING id",
                (scraped_at, "ok"),
            ).fetchone()
            assert row is not None
            run_id = row["id"]

            for p in products:
                conn.execute(
                    """
                    INSERT INTO products (ticker, product_name, first_seen_at, last_updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE
                        SET product_name = EXCLUDED.product_name,
                            last_updated_at = EXCLUDED.last_updated_at
                    """,
                    (p.ticker, p.product_name, scraped_at, scraped_at),
                )
                conn.execute(
                    """
                    INSERT INTO snapshots (
                        scrape_run_id, ticker, price, previous_price, price_change,
                        nav, nav_calculated, nav_rebate_premium,
                        nav_calculated_rebate_premium, weight, market_cap_weight, scraped_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        p.ticker,
                        p.price,
                        p.previous_price,
                        p.price_change,
                        p.nav,
                        p.nav_calculated,
                        p.nav_rebate_premium,
                        p.nav_calculated_rebate_premium,
                        weights.get(p.ticker),
                        market_cap_weights.get(p.ticker),
                        scraped_at,
                    ),
                )

        print(f"Scraped {len(products)} products (run_id={run_id})")

    except Exception as exc:
        # The DB itself may be what failed — never let this write mask the
        # original error or the non-zero exit code.
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO scrape_runs (scraped_at, status) VALUES (%s, %s)",
                    (scraped_at, "error"),
                )
        except Exception as db_exc:
            print(f"Could not record failed run: {db_exc}", file=sys.stderr)
        print(f"Scrape failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
