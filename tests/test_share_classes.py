"""Choosing between the A/B/C listings of the same company."""

import pytest

from app.portfolio import (
    WeightingMethod,
    allocate,
    apply_share_class,
    cheapest_share_classes,
    compare_share_classes,
    premium_pct,
)
from shared.models import ShareClassRow, SnapshotRow

# --- comparison ---


def test_compare_reports_cheapest_and_priciest(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    by_base = {
        c.base_ticker: c for c in compare_share_classes(sample_snapshots, sample_share_classes)
    }

    inve = by_base["INVE B"]
    assert inve.cheapest_ticker == "INVE A"
    assert inve.priciest_ticker == "INVE B"
    assert inve.spread_pct == pytest.approx((300 - 285) / 285 * 100)


def test_compare_ranks_tradeable_spreads_above_wider_illiquid_ones(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    """KINV's 25% spread is an artefact of a stale quote; INVE's 5% is real."""
    comparisons = compare_share_classes(sample_snapshots, sample_share_classes)

    assert [c.base_ticker for c in comparisons] == ["INVE B", "KINV B"]
    assert comparisons[0].spread_pct < comparisons[1].spread_pct


def test_compare_sorts_liquid_companies_by_widest_spread(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    liquid = [c.model_copy(update={"avg_volume": 500_000.0}) for c in sample_share_classes]

    spreads = [c.spread_pct for c in compare_share_classes(sample_snapshots, liquid)]

    assert spreads == sorted(spreads, reverse=True)


def test_compare_flags_thinly_traded_class(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    by_base = {
        c.base_ticker: c for c in compare_share_classes(sample_snapshots, sample_share_classes)
    }

    assert by_base["KINV B"].illiquid is True
    assert by_base["INVE B"].illiquid is False


def test_compare_skips_single_class_companies(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    bases = {c.base_ticker for c in compare_share_classes(sample_snapshots, sample_share_classes)}
    assert "BURE" not in bases


def test_compare_follows_the_exchange_list_filter(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    only_kinnevik = [s for s in sample_snapshots if s.ticker == "KINV B"]

    comparisons = compare_share_classes(only_kinnevik, sample_share_classes)

    assert [c.base_ticker for c in comparisons] == ["KINV B"]


def test_compare_without_data_is_empty(sample_snapshots: list[SnapshotRow]) -> None:
    assert compare_share_classes(sample_snapshots, []) == []


# --- automatic "cheapest" selection ---


def test_cheapest_picks_the_lower_priced_class(
    sample_share_classes: list[ShareClassRow],
) -> None:
    assert cheapest_share_classes(sample_share_classes)["INVE B"] == "INVE A"


def test_cheapest_refuses_an_illiquid_bargain(
    sample_share_classes: list[ShareClassRow],
) -> None:
    """KINV A is cheaper on paper but trades 41 shares a day — the quote is stale."""
    assert cheapest_share_classes(sample_share_classes)["KINV B"] == "KINV B"


def test_cheapest_ignores_classes_without_volume_data(
    sample_share_classes: list[ShareClassRow],
) -> None:
    """Unknown liquidity is treated as illiquid — never auto-bought on a guess."""
    unknown = [
        c.model_copy(update={"avg_volume": None}) if c.ticker == "INVE A" else c
        for c in sample_share_classes
    ]

    assert cheapest_share_classes(unknown)["INVE B"] == "INVE B"


def test_cheapest_without_any_liquid_class_omits_the_company(
    sample_share_classes: list[ShareClassRow],
) -> None:
    illiquid = [c.model_copy(update={"avg_volume": 5.0}) for c in sample_share_classes]

    assert cheapest_share_classes(illiquid) == {}


# --- applying the choice ---


def test_apply_reprices_and_renames(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    repriced = apply_share_class(sample_snapshots, sample_share_classes, {"INVE B": "INVE A"})
    inve = next(s for s in repriced if s.ticker == "INVE B")

    assert inve.price == 285.0
    assert inve.product_name == "Investor A"


def test_apply_keeps_the_ibindex_ticker(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    """NAV and holdings are reported per company, so lookups must still resolve."""
    repriced = apply_share_class(sample_snapshots, sample_share_classes, {"INVE B": "INVE A"})

    assert {s.ticker for s in repriced} == {s.ticker for s in sample_snapshots}


def test_apply_leaves_other_companies_untouched(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    repriced = apply_share_class(sample_snapshots, sample_share_classes, {"INVE B": "INVE A"})
    before = {s.ticker: s for s in sample_snapshots}

    for s in repriced:
        if s.ticker != "INVE B":
            assert s == before[s.ticker]


def test_apply_without_a_choice_is_a_no_op(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    assert apply_share_class(sample_snapshots, sample_share_classes, {}) == sample_snapshots


def test_apply_choosing_the_ibindex_class_is_a_no_op(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    repriced = apply_share_class(sample_snapshots, sample_share_classes, {"INVE B": "INVE B"})
    assert repriced == sample_snapshots


def test_apply_ignores_an_unknown_class(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    repriced = apply_share_class(sample_snapshots, sample_share_classes, {"INVE B": "INVE Z"})
    assert repriced == sample_snapshots


# --- effect on the portfolio ---


def test_cheaper_class_buys_more_shares(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    base = allocate(sample_snapshots, 100_000, method=WeightingMethod.EQUAL)
    repriced = allocate(
        apply_share_class(sample_snapshots, sample_share_classes, {"INVE B": "INVE A"}),
        100_000,
        method=WeightingMethod.EQUAL,
    )

    shares = {r.ticker: r.shares for r in base}
    cheaper = {r.ticker: r.shares for r in repriced}
    assert cheaper["INVE B"] > shares["INVE B"]
    assert cheaper["KINV B"] == shares["KINV B"]


def test_premium_is_measured_against_the_chosen_class(
    sample_snapshots: list[SnapshotRow], sample_share_classes: list[ShareClassRow]
) -> None:
    """Buying the cheaper class is buying the same NAV for less — a lower premium."""
    before = next(s for s in sample_snapshots if s.ticker == "INVE B")
    after = next(
        s
        for s in apply_share_class(sample_snapshots, sample_share_classes, {"INVE B": "INVE A"})
        if s.ticker == "INVE B"
    )

    base_premium = premium_pct(before)
    chosen_premium = premium_pct(after)
    assert base_premium is not None and chosen_premium is not None
    assert chosen_premium < base_premium
