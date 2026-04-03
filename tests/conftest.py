from datetime import datetime, timezone

import pytest

from shared.models import SnapshotRow

NOW = datetime.now(timezone.utc)


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
            nav_rebate_premium=-6.5,
            nav_calculated_rebate_premium=-5.0,
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
            nav_rebate_premium=7.1,
            nav_calculated_rebate_premium=3.4,
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
            nav_rebate_premium=-4.8,
            nav_calculated_rebate_premium=-7.0,
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
            nav_rebate_premium=-16.7,
            nav_calculated_rebate_premium=-13.8,
            weight=None,
            market_cap_weight=None,  # no data from Yahoo Finance
            scraped_at=NOW,
        ),
    ]
