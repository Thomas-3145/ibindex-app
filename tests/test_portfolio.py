from app.portfolio import allocate
from shared.models import SnapshotRow


def test_allocate_excludes_no_weight(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000)
    tickers = [r.ticker for r in results]
    assert "VNV" not in tickers


def test_allocate_includes_weighted_companies(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000)
    tickers = [r.ticker for r in results]
    assert "INVE B" in tickers
    assert "KINV B" in tickers
    assert "BURE" in tickers


def test_allocate_sums_to_capital(sample_snapshots: list[SnapshotRow]) -> None:
    capital = 100_000.0
    results = allocate(sample_snapshots, capital)
    total = sum(r.allocated_sek for r in results)
    assert abs(total - capital) < 0.01


def test_allocate_proportional_to_weight(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000)
    by_ticker = {r.ticker: r for r in results}
    # INVE B market_cap_weight 45.0, BURE 20.0 → ratio should be 2.25
    ratio = by_ticker["INVE B"].allocated_sek / by_ticker["BURE"].allocated_sek
    assert abs(ratio - (45.0 / 20.0)) < 0.01


def test_allocate_approx_shares(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000)
    for r in results:
        expected = r.allocated_sek / r.price
        assert abs(r.approx_shares - expected) < 0.001


def test_allocate_sorted_by_weight_descending(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000)
    weights = [r.weight for r in results]
    assert weights == sorted(weights, reverse=True)


def test_allocate_empty_snapshots() -> None:
    assert allocate([], 100_000) == []


def test_allocate_all_without_weight() -> None:
    from datetime import datetime, timezone

    snapshots = [
        SnapshotRow(
            ticker="X",
            product_name="X Corp",
            price=100.0,
            previous_price=None,
            price_change=None,
            nav=None,
            nav_calculated=None,
            nav_rebate_premium=None,
            nav_calculated_rebate_premium=None,
            weight=None,
            market_cap_weight=None,
            scraped_at=datetime.now(timezone.utc),
        )
    ]
    assert allocate(snapshots, 100_000) == []
