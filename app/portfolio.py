import math
from enum import Enum

from shared.models import AllocationResult, HoldingRow, SnapshotRow, UnderlyingAllocation


class WeightingMethod(Enum):
    MARKET_CAP = "Marknadsviktat"
    LOG_MARKET_CAP = "Logaritmiskt viktat"
    CAPPED = "Marknadsviktat med tak"
    EQUAL = "Likaviktat"


def allocate(
    snapshots: list[SnapshotRow],
    capital: float,
    method: WeightingMethod = WeightingMethod.MARKET_CAP,
    cap: float = 20.0,
) -> list[AllocationResult]:
    # Companies without market-cap data are excluded from every method,
    # including EQUAL, so all methods allocate over the same universe.
    eligible = [s for s in snapshots if s.market_cap_weight and s.price > 0]

    if not eligible:
        return []

    raw_weights = _compute_weights(eligible, method, cap)

    total = sum(raw_weights.values())
    results = []
    for s in eligible:
        w = raw_weights[s.ticker]
        allocated_sek = capital * (w / total)
        results.append(
            AllocationResult(
                ticker=s.ticker,
                product_name=s.product_name,
                price=s.price,
                weight=round(w / total * 100, 2),
                allocated_sek=round(allocated_sek, 2),
                approx_shares=round(allocated_sek / s.price, 4),
            )
        )

    return sorted(results, key=lambda r: r.weight, reverse=True)


def _compute_weights(
    snapshots: list[SnapshotRow],
    method: WeightingMethod,
    cap: float,
) -> dict[str, float]:
    if method == WeightingMethod.EQUAL:
        return {s.ticker: 1.0 for s in snapshots}

    assert all(s.market_cap_weight is not None for s in snapshots)

    if method == WeightingMethod.MARKET_CAP:
        return {s.ticker: s.market_cap_weight for s in snapshots}  # type: ignore[misc]

    if method == WeightingMethod.LOG_MARKET_CAP:
        return {s.ticker: math.log1p(s.market_cap_weight) for s in snapshots}  # type: ignore[arg-type]

    if method == WeightingMethod.CAPPED:
        return _apply_cap({s.ticker: s.market_cap_weight for s in snapshots}, cap)  # type: ignore[misc]

    return {s.ticker: 1.0 for s in snapshots}


def premium_pct(snapshot: SnapshotRow) -> float | None:
    """Premium (positive) or discount (negative) vs NAV, in percent."""
    nav = snapshot.nav or snapshot.nav_calculated
    if not nav or nav <= 0:
        return None
    return (snapshot.price - nav) / nav * 100


def expand_allocations(
    results: list[AllocationResult],
    snapshots: list[SnapshotRow],
    holdings: list[HoldingRow],
    expand_all: bool = False,
    premium_threshold: float = 0.0,
) -> list[UnderlyingAllocation]:
    """Replace investment companies with their listed holdings.

    With expand_all=False only companies trading above `premium_threshold`
    percent premium are expanded; with expand_all=True every company with
    holdings data is (full look-through). Only listed (LST) holdings are
    buyable, so each company's allocation is distributed over those — this
    implicitly spreads the unlisted part proportionally. Expansion is one
    level deep: a holding that is itself an investment company is kept as-is.
    """
    snap_by_ticker = {s.ticker: s for s in snapshots}

    listed_by_owner: dict[str, list[HoldingRow]] = {}
    for h in holdings:
        if h.category == "LST" and h.value > 0:
            listed_by_owner.setdefault(h.owner_ticker, []).append(h)

    merged: dict[str, UnderlyingAllocation] = {}

    def add(key: str, name: str, ticker: str | None, sek: float, via: str) -> None:
        entry = merged.get(key)
        if entry is None:
            merged[key] = UnderlyingAllocation(
                name=name, ticker=ticker, allocated_sek=sek, weight=0.0, via=[via]
            )
        else:
            entry.allocated_sek += sek
            if via not in entry.via:
                entry.via.append(via)

    for r in results:
        listed = listed_by_owner.get(r.ticker, [])
        should_expand = bool(listed)
        if not expand_all:
            snapshot = snap_by_ticker.get(r.ticker)
            premium = premium_pct(snapshot) if snapshot else None
            should_expand = bool(listed) and premium is not None and premium > premium_threshold

        if not should_expand:
            add(r.ticker, r.product_name, r.ticker, r.allocated_sek, "Direkt")
            continue

        total_value = sum(h.value for h in listed)
        for h in listed:
            add(
                h.holding_ticker or h.holding_name,
                h.holding_name,
                h.holding_ticker,
                r.allocated_sek * (h.value / total_value),
                r.product_name,
            )

    total = sum(e.allocated_sek for e in merged.values())
    entries = sorted(merged.values(), key=lambda e: e.allocated_sek, reverse=True)
    for e in entries:
        e.weight = round(e.allocated_sek / total * 100, 2)
        e.allocated_sek = round(e.allocated_sek, 2)
    return entries


def _apply_cap(weights: dict[str, float], cap_pct: float) -> dict[str, float]:
    total = sum(weights.values())
    cap = cap_pct / 100 * total
    result = dict(weights)
    capped: set[str] = set()

    # Cap and freeze, redistributing only to unfrozen tickers. Without the
    # freeze the excess bounces between already-capped tickers and never
    # settles when the cap is tight or infeasible (cap * n < 100%).
    while True:
        over = {t for t, w in result.items() if w > cap and t not in capped}
        if not over:
            break
        excess = sum(result[t] - cap for t in over)
        for t in over:
            result[t] = cap
        capped |= over

        free_total = sum(w for t, w in result.items() if t not in capped)
        if free_total == 0:
            # Infeasible cap: everything sits at the cap; normalization in
            # allocate() turns this into an equal weighting.
            break
        for t in result:
            if t not in capped:
                result[t] += excess * (result[t] / free_total)

    return result
