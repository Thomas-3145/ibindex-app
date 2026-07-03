import math
from enum import Enum

from shared.models import AllocationResult, SnapshotRow


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
