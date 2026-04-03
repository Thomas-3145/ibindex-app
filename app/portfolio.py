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
        return {s.ticker: math.log1p(s.market_cap_weight) for s in snapshots}  # type: ignore[misc]

    if method == WeightingMethod.CAPPED:
        return _apply_cap({s.ticker: s.market_cap_weight for s in snapshots}, cap)  # type: ignore[misc]

    return {s.ticker: 1.0 for s in snapshots}


def _apply_cap(weights: dict[str, float], cap_pct: float) -> dict[str, float]:
    total = sum(weights.values())
    cap = cap_pct / 100 * total
    result = dict(weights)

    for _ in range(100):  # iterate until stable
        over = {t: w for t, w in result.items() if w > cap}
        if not over:
            break
        excess = sum(w - cap for w in over.values())
        under = {t: w for t, w in result.items() if w <= cap}
        under_total = sum(under.values())
        for t in over:
            result[t] = cap
        if under_total > 0:
            for t in under:
                result[t] += excess * (result[t] / under_total)

    return result
