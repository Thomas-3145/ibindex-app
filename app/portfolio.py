import math
from enum import Enum

from shared.models import AllocationResult, HoldingRow, SnapshotRow, UnderlyingAllocation


class WeightingMethod(Enum):
    MARKET_CAP = "Marknadsviktat"
    LOG_MARKET_CAP = "Logaritmiskt viktat"
    CAPPED = "Marknadsviktat med tak"
    EQUAL = "Likaviktat"


class InfeasibleCapError(ValueError):
    """Raised when too few companies are selected for the requested cap."""

    def __init__(self, cap_pct: float, company_count: int) -> None:
        self.cap_pct = cap_pct
        self.company_count = company_count
        self.minimum_cap_pct = 100.0 / company_count
        super().__init__(
            f"A {cap_pct:g}% cap is infeasible for {company_count} companies; "
            f"the minimum is {self.minimum_cap_pct:.2f}%"
        )


def allocate(
    snapshots: list[SnapshotRow],
    capital: float,
    method: WeightingMethod = WeightingMethod.MARKET_CAP,
    cap: float = 20.0,
) -> list[AllocationResult]:
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("capital must be a positive finite amount")

    # Equal weighting does not depend on Yahoo Finance data. The other
    # methods require a positive market-cap weight to produce a valid ratio.
    eligible = [
        s
        for s in snapshots
        if s.price > 0 and (method == WeightingMethod.EQUAL or (s.market_cap_weight or 0) > 0)
    ]

    if not eligible:
        return []

    raw_weights = _compute_weights(eligible, method, cap)

    total = sum(raw_weights.values())
    normalized_weights = [raw_weights[s.ticker] / total for s in eligible]
    target_amounts = _round_to_total([capital * weight for weight in normalized_weights], capital)
    display_weights = _round_to_total([weight * 100 for weight in normalized_weights], 100.0)

    results = []
    for s, target_sek, weight_pct in zip(eligible, target_amounts, display_weights, strict=True):
        shares = math.floor(target_sek / s.price)
        invested_sek = round(shares * s.price, 2)
        results.append(
            AllocationResult(
                ticker=s.ticker,
                product_name=s.product_name,
                price=s.price,
                weight=weight_pct,
                target_sek=target_sek,
                allocated_sek=invested_sek,
                shares=shares,
            )
        )

    return sorted(results, key=lambda r: r.weight, reverse=True)


def _round_to_total(values: list[float], total: float) -> list[float]:
    """Round non-negative values to cents while preserving the rounded total."""
    if not values:
        return []

    exact_cents = [value * 100 for value in values]
    cents = [math.floor(value + 1e-9) for value in exact_cents]
    remaining = round(total * 100) - sum(cents)
    by_largest_remainder = sorted(
        range(len(values)),
        key=lambda index: exact_cents[index] - cents[index],
        reverse=True,
    )
    for index in by_largest_remainder[:remaining]:
        cents[index] += 1

    return [value / 100 for value in cents]


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
    """Premium (positive) or discount (negative) vs current estimated NAV.

    ibindex's ``netAssetValueRebatePremium`` uses the opposite convention:
    positive means discount. Calculating from price and the estimated NAV
    keeps this app's public convention explicit. Reported NAV is used only
    when the estimated value is unavailable.
    """
    nav = snapshot.nav_calculated or snapshot.nav
    if not nav or nav <= 0:
        return None
    return (snapshot.price - nav) / nav * 100


def expand_allocations(
    results: list[AllocationResult],
    snapshots: list[SnapshotRow],
    holdings: list[HoldingRow],
    expand_all: bool = False,
    premium_threshold: float = 0.0,
) -> tuple[list[UnderlyingAllocation], list[tuple[str, float]], list[str]]:
    """Replace investment companies with their listed holdings.

    With expand_all=False only companies trading above `premium_threshold`
    percent premium are expanded; with expand_all=True every company with
    holdings data is (full look-through). Only listed (LST) holdings are
    buyable, so each company's allocation is distributed over those — this
    implicitly spreads the unlisted part proportionally. Expansion is one
    level deep: a holding that is itself an investment company is kept as-is.

    Returns the expanded allocations; for premium-based expansion, the
    (product_name, premium_pct) of each company that was replaced; and the
    names of companies that should have been expanded but lack listed
    holdings data.
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

    replaced: list[tuple[str, float]] = []
    unavailable: list[str] = []
    for r in results:
        listed = listed_by_owner.get(r.ticker, [])
        snapshot = snap_by_ticker.get(r.ticker)
        premium = premium_pct(snapshot) if snapshot else None
        wants_expansion = expand_all or (premium is not None and premium > premium_threshold)
        should_expand = wants_expansion and bool(listed)

        if wants_expansion and not listed:
            unavailable.append(r.product_name)
        elif should_expand and not expand_all:
            assert premium is not None
            replaced.append((r.product_name, premium))

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

    invested_total = sum(e.allocated_sek for e in merged.values())
    portfolio_capital = sum(r.target_sek for r in results)
    entries = sorted(merged.values(), key=lambda e: e.allocated_sek, reverse=True)
    rounded_amounts = _round_to_total([e.allocated_sek for e in entries], invested_total)
    invested_weight = invested_total / portfolio_capital * 100
    rounded_weights = _round_to_total(
        [e.allocated_sek / portfolio_capital * 100 for e in entries], invested_weight
    )
    for e, amount, weight in zip(entries, rounded_amounts, rounded_weights, strict=True):
        e.weight = weight
        e.allocated_sek = amount
    return entries, replaced, unavailable


def _apply_cap(weights: dict[str, float], cap_pct: float) -> dict[str, float]:
    if not weights:
        return {}
    if not 0 < cap_pct <= 100:
        raise ValueError("cap_pct must be greater than 0 and at most 100")
    if cap_pct * len(weights) < 100 - 1e-9:
        raise InfeasibleCapError(cap_pct, len(weights))

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
            break
        for t in result:
            if t not in capped:
                result[t] += excess * (result[t] / free_total)

    return result
