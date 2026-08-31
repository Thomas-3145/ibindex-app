import json
import sys
from datetime import UTC, datetime

import requests
import yfinance as yf  # type: ignore[import-untyped]
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from shared.constants import SHARE_CLASSES
from shared.db import get_connection, init_db
from shared.models import HoldingResponse, ProductResponse, ShareClassRow, WeightResponse

PRODUCTS_URL = "https://ibindex.se/ibi/index/getProducts.req"
WEIGHTS_URL = "https://ibindex.se/ibi/index/getProductWeights.req"
HOLDINGS_URL = "https://ibindex.se/ibi/company/getHoldings.req"
TIMEOUT = 10
MINIMUM_COVERAGE = 0.5

# Companies not listed on Nasdaq Stockholm, where the ".ST" rule fails.
YAHOO_TICKER_OVERRIDES = {
    "SON": "SON.LS",  # Sonae, SGPS — Euronext Lisbon
}


def _build_http_session() -> requests.Session:
    """Create a session that retries transient failures from the ibindex API."""
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


HTTP = _build_http_session()


def to_yahoo_ticker(ibindex_ticker: str) -> str:
    override = YAHOO_TICKER_OVERRIDES.get(ibindex_ticker)
    if override:
        return override
    return ibindex_ticker.replace(" ", "-") + ".ST"


def fetch_products() -> list[ProductResponse]:
    response = HTTP.get(PRODUCTS_URL, timeout=TIMEOUT)
    response.raise_for_status()
    return [ProductResponse.model_validate(item) for item in response.json()]


def fetch_weights() -> dict[str, float]:
    response = HTTP.get(WEIGHTS_URL, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if not data:
        return {}
    weights = [WeightResponse.model_validate(item) for item in data]
    return {w.ticker: w.weight for w in weights}


def fetch_holdings(ticker: str) -> list[HoldingResponse]:
    # The ibindex API expects the ticker as a JSON-encoded string body and
    # rejects plain "application/json" — the charset suffix is required.
    response = HTTP.post(
        HOLDINGS_URL,
        data=json.dumps(ticker),
        headers={"Content-Type": "application/json;charset=UTF-8"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return [HoldingResponse.model_validate(item) for item in response.json() or []]


def _rate_to_sek(currency: str, cache: dict[str, float]) -> float:
    if currency not in cache:
        cache[currency] = float(yf.Ticker(f"{currency}SEK=X").fast_info["last_price"])
    return cache[currency]


def fetch_market_cap_weights(products: list[ProductResponse]) -> dict[str, float]:
    market_caps: dict[str, float] = {}
    fx_to_sek: dict[str, float] = {"SEK": 1.0}

    for p in products:
        yahoo_ticker = to_yahoo_ticker(p.ticker)
        try:
            # fast_info, never .info: .info returns no sharesOutstanding at
            # all for some tickers (INVE B — the largest company in the
            # index), and where it does return one it counts only the quoted
            # share class, halving the market cap of every company with a
            # separate A class (INDU C, LUND B). fast_info["market_cap"] is
            # priced off all classes.
            info = yf.Ticker(yahoo_ticker).fast_info
            market_cap = info["market_cap"]
            if not market_cap:
                print(f"No market cap for {p.ticker} ({yahoo_ticker})", file=sys.stderr)
                continue
            # ibindex reports foreign listings (e.g. SON) in their native
            # currency, and so does Yahoo — convert to SEK to be comparable.
            currency = info["currency"] or "SEK"
            market_caps[p.ticker] = float(market_cap) * _rate_to_sek(currency, fx_to_sek)
        except Exception as exc:
            print(f"Market cap unavailable for {p.ticker} ({yahoo_ticker}): {exc}", file=sys.stderr)

    total = sum(market_caps.values())
    if total == 0:
        return {}

    return {ticker: (cap / total) * 100 for ticker, cap in market_caps.items()}


def fetch_share_classes(
    products: list[ProductResponse], scraped_at: datetime
) -> list[ShareClassRow]:
    """Price every listed class of the multi-class companies in the index.

    ibindex quotes one class per company, so the alternatives come from
    Yahoo. All classes — the ibindex one included — are priced from the same
    source so the spread between them is a like-for-like comparison.
    Average volume travels with the price because thinly traded A shares
    carry stale quotes that would otherwise look like a free discount.
    """
    rows: list[ShareClassRow] = []

    for p in products:
        for ticker in SHARE_CLASSES.get(p.ticker, []):
            yahoo_ticker = to_yahoo_ticker(ticker)
            try:
                history = yf.Ticker(yahoo_ticker).history(period="1mo")
                if history.empty:
                    print(f"No quotes for share class {ticker}", file=sys.stderr)
                    continue
                price = float(history["Close"].iloc[-1])
                if price <= 0:
                    continue
                rows.append(
                    ShareClassRow(
                        base_ticker=p.ticker,
                        ticker=ticker,
                        price=price,
                        avg_volume=float(history["Volume"].mean()),
                        scraped_at=scraped_at,
                    )
                )
            except Exception as exc:
                print(f"Share class unavailable for {ticker}: {exc}", file=sys.stderr)

    return rows


def require_minimum_coverage(label: str, successful: int, total: int) -> None:
    """Reject a dataset that would make a major app feature misleading."""
    if total <= 0:
        raise RuntimeError(f"{label}: source returned no companies")
    if successful < total * MINIMUM_COVERAGE:
        raise RuntimeError(
            f"{label} available for only {successful} of {total} companies — aborting run"
        )


def main() -> None:
    init_db()

    scraped_at = datetime.now(UTC)

    try:
        products = fetch_products()
        if not products:
            raise RuntimeError("ibindex returned no products — aborting run")
        weights = fetch_weights()

        print("Hämtar marknadsvärden från Yahoo Finance...")
        market_cap_weights = fetch_market_cap_weights(products)
        print(f"Marknadsvikt beräknad för {len(market_cap_weights)} bolag")

        # A broken yfinance integration would otherwise record an 'ok' run
        # with no weights, silently emptying the app's allocation view.
        require_minimum_coverage("Market cap weights", len(market_cap_weights), len(products))

        print("Hämtar innehav från ibindex.se...")
        # One flaky request should cost that company's holdings, not the
        # whole evening's snapshot.
        holdings: dict[str, list[HoldingResponse]] = {}
        holdings_fetches_ok = 0
        for p in products:
            try:
                holdings[p.ticker] = fetch_holdings(p.ticker)
                holdings_fetches_ok += 1
            except Exception as exc:
                print(f"Holdings fetch failed for {p.ticker}: {exc}", file=sys.stderr)
                holdings[p.ticker] = []
        require_minimum_coverage("Holdings", holdings_fetches_ok, len(products))
        print(f"Innehav hämtade för {sum(1 for h in holdings.values() if h)} bolag")

        print("Hämtar alternativa aktieslag...")
        # Best-effort: the A/B comparison is a side feature, so a Yahoo
        # outage here must not cost the evening's prices and holdings.
        share_classes = fetch_share_classes(products, scraped_at)
        print(f"Aktieslag prissatta: {len(share_classes)}")

        with get_connection() as conn, conn.cursor() as cur:
            row = cur.execute(
                "INSERT INTO scrape_runs (scraped_at, status) VALUES (%s, %s) RETURNING id",
                (scraped_at, "ok"),
            ).fetchone()
            assert row is not None
            run_id = row["id"]

            cur.executemany(
                """
                INSERT INTO products (ticker, product_name, first_seen_at, last_updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE
                    SET product_name = EXCLUDED.product_name,
                        last_updated_at = EXCLUDED.last_updated_at
                """,
                [(p.ticker, p.product_name, scraped_at, scraped_at) for p in products],
            )
            cur.executemany(
                """
                INSERT INTO snapshots (
                    scrape_run_id, ticker, price, previous_price, price_change,
                    nav, nav_calculated, nav_rebate_premium,
                    nav_calculated_rebate_premium, weight, market_cap_weight, scraped_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
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
                    )
                    for p in products
                ],
            )
            holding_rows = [
                (
                    run_id,
                    p.ticker,
                    h.holding_ticker,
                    h.holding_name,
                    h.exchange,
                    h.value,
                    h.category,
                    h.category_name,
                    scraped_at,
                )
                for p in products
                for h in holdings[p.ticker]
            ]
            if holding_rows:
                cur.executemany(
                    """
                    INSERT INTO holdings (
                        scrape_run_id, owner_ticker, holding_ticker, holding_name,
                        exchange, value, category, category_name, scraped_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    holding_rows,
                )
            if share_classes:
                cur.executemany(
                    """
                    INSERT INTO share_classes (
                        scrape_run_id, base_ticker, ticker, price, avg_volume, scraped_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (run_id, sc.base_ticker, sc.ticker, sc.price, sc.avg_volume, sc.scraped_at)
                        for sc in share_classes
                    ],
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
