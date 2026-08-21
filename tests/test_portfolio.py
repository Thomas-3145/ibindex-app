import math
from datetime import UTC

import pytest

from app.portfolio import (
    InfeasibleCapError,
    WeightingMethod,
    _apply_cap,
    allocate,
    expand_allocations,
    premium_pct,
)
from shared.models import HoldingRow, SnapshotRow


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
    invested = sum(r.allocated_sek for r in results)
    assert invested <= capital
    assert round(sum(r.target_sek for r in results), 2) == capital


def test_allocate_preserves_odd_capital_to_the_cent(
    sample_snapshots: list[SnapshotRow],
) -> None:
    capital = 100_000.01
    results = allocate(sample_snapshots, capital, method=WeightingMethod.EQUAL)

    assert round(sum(r.target_sek for r in results), 2) == capital
    assert round(sum(r.weight for r in results), 2) == 100.0


def test_allocate_rejects_invalid_capital(sample_snapshots: list[SnapshotRow]) -> None:
    with pytest.raises(ValueError, match="capital"):
        allocate(sample_snapshots, 0)


def test_allocate_proportional_to_weight(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000)
    by_ticker = {r.ticker: r for r in results}
    # INVE B market_cap_weight 45.0, BURE 20.0 → ratio should be 2.25
    ratio = by_ticker["INVE B"].target_sek / by_ticker["BURE"].target_sek
    assert abs(ratio - (45.0 / 20.0)) < 0.01


def test_allocate_returns_buyable_whole_shares(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000)
    for r in results:
        assert r.shares == math.floor(r.target_sek / r.price)
        assert r.allocated_sek == round(r.shares * r.price, 2)
        assert r.allocated_sek <= r.target_sek


def test_allocate_sorted_by_weight_descending(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000)
    weights = [r.weight for r in results]
    assert weights == sorted(weights, reverse=True)


def test_allocate_empty_snapshots() -> None:
    assert allocate([], 100_000) == []


def test_equal_weighting_allocates_evenly(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 90_000, method=WeightingMethod.EQUAL)
    assert len(results) == 4
    for r in results:
        assert abs(r.target_sek - 22_500) < 0.01


def test_log_weighting_less_concentrated_but_same_order(
    sample_snapshots: list[SnapshotRow],
) -> None:
    results = {
        r.ticker: r
        for r in allocate(sample_snapshots, 100_000, method=WeightingMethod.LOG_MARKET_CAP)
    }
    # log dampens the spread: the largest shrinks, the smallest grows
    assert results["INVE B"].weight < 45.0
    assert results["BURE"].weight > 20.0
    assert results["INVE B"].weight > results["KINV B"].weight > results["BURE"].weight


def test_capped_weighting_respects_cap(sample_snapshots: list[SnapshotRow]) -> None:
    results = allocate(sample_snapshots, 100_000, method=WeightingMethod.CAPPED, cap=40.0)
    by_ticker = {r.ticker: r for r in results}
    # INVE B (45%) is capped at 40, the 5% excess goes to KINV B and BURE
    # proportionally (35/55 and 20/55)
    assert by_ticker["INVE B"].weight == 40.0
    assert abs(by_ticker["KINV B"].weight - (35 + 5 * 35 / 55)) < 0.01
    assert abs(by_ticker["BURE"].weight - (20 + 5 * 20 / 55)) < 0.01


def test_capped_weighting_sums_to_capital(sample_snapshots: list[SnapshotRow]) -> None:
    capital = 100_000.0
    results = allocate(sample_snapshots, capital, method=WeightingMethod.CAPPED, cap=40.0)
    assert round(sum(r.target_sek for r in results), 2) == capital


def test_apply_cap_cascading_redistribution() -> None:
    # capping A pushes B over the cap, requiring a second pass
    result = _apply_cap({"A": 60.0, "B": 25.0, "C": 15.0}, 35.0)
    assert abs(result["A"] - 35.0) < 1e-9
    assert abs(result["B"] - 35.0) < 1e-9
    assert abs(result["C"] - 30.0) < 1e-9


def test_apply_cap_rejects_infeasible_cap() -> None:
    with pytest.raises(InfeasibleCapError) as exc_info:
        _apply_cap({"A": 60.0, "B": 25.0, "C": 15.0}, 30.0)

    assert exc_info.value.company_count == 3
    assert abs(exc_info.value.minimum_cap_pct - 100 / 3) < 1e-9


def test_apply_cap_noop_when_under_cap() -> None:
    weights = {"A": 30.0, "B": 40.0, "C": 30.0}
    assert _apply_cap(weights, 50.0) == weights


def test_allocate_all_without_weight() -> None:
    from datetime import datetime

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
            scraped_at=datetime.now(UTC),
        )
    ]
    assert allocate(snapshots, 100_000) == []


# --- premium expansion / look-through ---
# Estimated-NAV premiums: INVE B +5.26%, KINV B +3.45%, BURE -6.98% (discount)


def test_premium_pct_sign(sample_snapshots: list[SnapshotRow]) -> None:

    by_ticker = {s.ticker: s for s in sample_snapshots}
    inve = premium_pct(by_ticker["INVE B"])
    bure = premium_pct(by_ticker["BURE"])
    assert inve is not None and inve > 0  # trades above NAV
    assert bure is not None and bure < 0  # trades below NAV


def test_premium_pct_prefers_current_estimated_nav(
    sample_snapshots: list[SnapshotRow],
) -> None:
    snapshot = sample_snapshots[0].model_copy(update={"nav": 250.0, "nav_calculated": 350.0})

    premium = premium_pct(snapshot)

    assert premium is not None and premium < 0


def test_expand_replaces_premium_companies_only(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:

    results = allocate(sample_snapshots, 100_000)
    expanded, _, _ = expand_allocations(results, sample_snapshots, sample_holdings)
    names = {e.name for e in expanded}
    assert "Atlas Copco A" in names and "Tele2 B" in names
    assert "Investor B" not in names and "Kinnevik B" not in names
    assert "Bure Equity" in names  # discount -> kept


def test_expand_excludes_unlisted_and_debt(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:

    results = allocate(sample_snapshots, 100_000)
    expanded, _, _ = expand_allocations(results, sample_snapshots, sample_holdings)
    names = {e.name for e in expanded}
    assert "Mölnlycke" not in names
    assert "Nettoskuld" not in names


def test_expand_preserves_capital(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:

    results = allocate(sample_snapshots, 100_000)
    expanded, _, _ = expand_allocations(results, sample_snapshots, sample_holdings)
    invested = round(sum(r.allocated_sek for r in results), 2)
    cash = round(100_000 - invested, 2)
    assert round(sum(e.allocated_sek for e in expanded), 2) == invested
    assert round(sum(e.weight for e in expanded) + cash / 100_000 * 100, 2) == 100.0


def test_expand_aggregates_shared_holdings(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:

    results = allocate(sample_snapshots, 100_000)
    by_ticker = {r.ticker: r for r in results}
    expanded, _, _ = expand_allocations(results, sample_snapshots, sample_holdings)
    abb = next(e for e in expanded if e.name == "ABB")
    # ABB via both owners: 300/900 of Investor's + 100/200 of Kinnevik's allocation
    expected = by_ticker["INVE B"].allocated_sek * (300 / 900) + by_ticker[
        "KINV B"
    ].allocated_sek * (100 / 200)
    assert abs(abb.allocated_sek - expected) < 0.05
    assert set(abb.via) == {"Investor B", "Kinnevik B"}


def test_expand_respects_threshold(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:

    results = allocate(sample_snapshots, 100_000)
    expanded, replaced, _ = expand_allocations(
        results, sample_snapshots, sample_holdings, premium_threshold=10.0
    )
    # both premiums are ~7.14% < 10% -> nothing expanded
    assert {e.name for e in expanded} == {"Investor B", "Kinnevik B", "Bure Equity"}
    assert all(e.via == ["Direkt"] for e in expanded)
    assert replaced == []


def test_expand_reports_replaced_companies(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:
    results = allocate(sample_snapshots, 100_000)
    _, replaced, _ = expand_allocations(results, sample_snapshots, sample_holdings)
    names = {name for name, _ in replaced}
    assert names == {"Investor B", "Kinnevik B"}
    assert all(premium > 0 for _, premium in replaced)


def test_expand_keeps_premium_company_without_holdings(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:

    without_kinv = [h for h in sample_holdings if h.owner_ticker != "KINV B"]
    results = allocate(sample_snapshots, 100_000)
    expanded, _, unavailable = expand_allocations(results, sample_snapshots, without_kinv)
    kinv = next(e for e in expanded if e.name == "Kinnevik B")
    assert kinv.via == ["Direkt"]
    assert unavailable == ["Kinnevik B"]


def test_expand_all_is_full_look_through(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:

    results = allocate(sample_snapshots, 100_000)
    expanded, _, unavailable = expand_allocations(
        results, sample_snapshots, sample_holdings, expand_all=True
    )
    names = {e.name for e in expanded}
    assert "Vitrolife" in names  # BURE expanded despite discount
    assert "Bure Equity" not in names
    assert unavailable == []


def test_expand_all_reports_missing_listed_holdings(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:
    results = allocate(sample_snapshots, 100_000)
    without_bure = [h for h in sample_holdings if h.owner_ticker != "BURE"]

    expanded, _, unavailable = expand_allocations(
        results, sample_snapshots, without_bure, expand_all=True
    )

    assert "Bure Equity" in {e.name for e in expanded}
    assert unavailable == ["Bure Equity"]
