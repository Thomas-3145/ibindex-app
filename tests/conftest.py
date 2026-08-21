from datetime import UTC, datetime

import pytest

from shared.models import HoldingRow, SnapshotRow

NOW = datetime.now(UTC)


def _holding(
    owner: str,
    name: str,
    value: float,
    ticker: str | None = None,
    category: str = "LST",
    category_name: str = "Noterade",
) -> HoldingRow:
    return HoldingRow(
        owner_ticker=owner,
        holding_ticker=ticker,
        holding_name=name,
        exchange="OMX_STOCKHOLM" if category == "LST" else None,
        value=value,
        category=category,
        category_name=category_name,
        scraped_at=NOW,
    )


@pytest.fixture
def sample_holdings() -> list[HoldingRow]:
    return [
        # INVE B: 900 listed, 100 unlisted, -50 net debt
        _holding("INVE B", "Atlas Copco A", 600.0, ticker="ATCO A"),
        _holding("INVE B", "ABB", 300.0, ticker="ABB"),
        _holding("INVE B", "Mölnlycke", 100.0, category="ULT", category_name="Onoterade"),
        _holding("INVE B", "Nettoskuld", -50.0, category="C&D", category_name="Kassa och Skuld"),
        # KINV B: 200 listed, ABB shared with INVE B
        _holding("KINV B", "Tele2 B", 100.0, ticker="TEL2 B"),
        _holding("KINV B", "ABB", 100.0, ticker="ABB"),
        # BURE: listed holdings, but BURE trades at a discount
        _holding("BURE", "Vitrolife", 50.0, ticker="VITR"),
    ]


@pytest.fixture
def sample_snapshots() -> list[SnapshotRow]:
    return [
        SnapshotRow(
            ticker="INVE B",
            product_name="Investor B",
            price=300.0,
            previous_price=298.0,
            price_change=2.0,
            nav=280.0,
            nav_calculated=285.0,
            nav_rebate_premium=-7.14,
            nav_calculated_rebate_premium=-5.26,
            weight=10.5,
            market_cap_weight=45.0,
            scraped_at=NOW,
        ),
        SnapshotRow(
            ticker="KINV B",
            product_name="Kinnevik B",
            price=150.0,
            previous_price=148.0,
            price_change=2.0,
            nav=140.0,
            nav_calculated=145.0,
            nav_rebate_premium=-7.14,
            nav_calculated_rebate_premium=-3.45,
            weight=8.0,
            market_cap_weight=35.0,
            scraped_at=NOW,
        ),
        SnapshotRow(
            ticker="BURE",
            product_name="Bure Equity",
            price=200.0,
            previous_price=200.0,
            price_change=0.0,
            nav=210.0,
            nav_calculated=215.0,
            nav_rebate_premium=4.76,
            nav_calculated_rebate_premium=6.98,
            weight=7.0,
            market_cap_weight=20.0,
            scraped_at=NOW,
        ),
        SnapshotRow(
            ticker="VNV",
            product_name="VNV Global",
            price=50.0,
            previous_price=50.0,
            price_change=0.0,
            nav=60.0,
            nav_calculated=58.0,
            nav_rebate_premium=16.67,
            nav_calculated_rebate_premium=13.79,
            weight=None,
            market_cap_weight=None,  # no data from Yahoo Finance
            scraped_at=NOW,
        ),
    ]
