"""Pricing the alternative share classes from Yahoo."""

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pytest

from scraper.main import fetch_share_classes
from shared.models import ProductResponse

NOW = datetime.now(UTC)


def _product(ticker: str) -> ProductResponse:
    return ProductResponse(
        product=ticker,
        productName=ticker,
        price=100.0,
        previousPrice=100.0,
        priceChange=0.0,
        netAssetValue=100.0,
        netAssetValueCalculated=100.0,
        netAssetValueRebatePremium=0.0,
        netAssetValueCalculatedRebatePremium=0.0,
    )


def _history(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": closes, "Volume": volumes})


def test_prices_every_class_of_a_multi_class_company(fake_yf: dict[str, Any]) -> None:
    fake_yf["quotes"].update(
        {
            "INVE-A.ST": {"history": _history([405.0, 409.0], [300_000, 456_934])},
            "INVE-B.ST": {"history": _history([410.0, 413.1], [2_000_000, 2_616_480])},
        }
    )

    rows = fetch_share_classes([_product("INVE B")], NOW)

    by_ticker = {r.ticker: r for r in rows}
    assert set(by_ticker) == {"INVE A", "INVE B"}
    # Latest close, not the mean — the price you would pay today.
    assert by_ticker["INVE A"].price == pytest.approx(409.0)
    assert by_ticker["INVE A"].base_ticker == "INVE B"
    # Volume is averaged over the window so one quiet day is not mistaken
    # for a permanently illiquid listing.
    assert by_ticker["INVE A"].avg_volume == pytest.approx(378_467.0)


def test_single_class_companies_are_not_fetched(fake_yf: dict[str, Any]) -> None:
    assert fetch_share_classes([_product("BURE")], NOW) == []


def test_delisted_class_is_skipped_without_failing_the_run(fake_yf: dict[str, Any]) -> None:
    fake_yf["quotes"]["INVE-B.ST"] = {"history": _history([413.1], [2_616_480])}
    # INVE-A.ST is absent, which the fake returns as an empty frame.

    rows = fetch_share_classes([_product("INVE B")], NOW)

    assert [r.ticker for r in rows] == ["INVE B"]


def test_thinly_traded_class_keeps_its_low_volume(fake_yf: dict[str, Any]) -> None:
    """SVOL A trades ~41 shares a day; the volume must survive to the app."""
    fake_yf["quotes"].update(
        {
            "SVOL-A.ST": {"history": _history([96.5], [41.0])},
            "SVOL-B.ST": {"history": _history([57.5], [135_282.0])},
        }
    )

    rows = {r.ticker: r for r in fetch_share_classes([_product("SVOL B")], NOW)}

    assert rows["SVOL A"].avg_volume == pytest.approx(41.0)
    assert rows["SVOL A"].price > rows["SVOL B"].price


def test_all_rows_share_the_run_timestamp(fake_yf: dict[str, Any]) -> None:
    fake_yf["quotes"].update(
        {
            "INVE-A.ST": {"history": _history([409.0], [456_934])},
            "INVE-B.ST": {"history": _history([413.1], [2_616_480])},
        }
    )

    rows = fetch_share_classes([_product("INVE B")], NOW)

    assert {r.scraped_at for r in rows} == {NOW}
