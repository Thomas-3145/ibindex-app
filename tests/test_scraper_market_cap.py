"""Market cap weighting: the numbers every non-equal-weighted portfolio rests on.

Regression cover for the bug where ``.info["sharesOutstanding"]`` was used
instead of ``fast_info["market_cap"]``. That silently dropped INVE B — the
largest company in the index, two thirds of it by market cap — because Yahoo
returns no sharesOutstanding for that ticker, and halved INDU C and LUND B
because sharesOutstanding counts only the quoted share class.
"""

from typing import Any

import pytest

from scraper.main import fetch_market_cap_weights
from shared.models import ProductResponse


def _product(ticker: str, price: float = 100.0) -> ProductResponse:
    return ProductResponse(
        product=ticker,
        productName=ticker,
        price=price,
        previousPrice=price,
        priceChange=0.0,
        netAssetValue=price,
        netAssetValueCalculated=price,
        netAssetValueRebatePremium=0.0,
        netAssetValueCalculatedRebatePremium=0.0,
    )


def test_weights_are_proportional_to_market_cap(fake_yf: dict[str, Any]) -> None:
    fake_yf["quotes"].update(
        {
            "A.ST": {"market_cap": 750e9, "currency": "SEK"},
            "B.ST": {"market_cap": 250e9, "currency": "SEK"},
        }
    )

    weights = fetch_market_cap_weights([_product("A"), _product("B")])

    assert weights["A"] == pytest.approx(75.0)
    assert weights["B"] == pytest.approx(25.0)


def test_never_falls_back_to_shares_outstanding(fake_yf: dict[str, Any]) -> None:
    """`.info` omits sharesOutstanding for INVE B and undercounts share classes."""
    fake_yf["quotes"]["INVE-B.ST"] = {"market_cap": 1_265e9, "currency": "SEK"}

    weights = fetch_market_cap_weights([_product("INVE B")])

    assert weights == {"INVE B": pytest.approx(100.0)}
    assert fake_yf["info_reads"] == []


def test_largest_company_is_not_dropped(fake_yf: dict[str, Any]) -> None:
    """The exact shape of the original bug, scaled to the real index."""
    fake_yf["quotes"].update(
        {
            "INVE-B.ST": {"market_cap": 1_265.5e9, "currency": "SEK"},
            "INDU-C.ST": {"market_cap": 232.4e9, "currency": "SEK"},
            "BURE.ST": {"market_cap": 23.5e9, "currency": "SEK"},
        }
    )

    weights = fetch_market_cap_weights([_product("INVE B"), _product("INDU C"), _product("BURE")])

    assert set(weights) == {"INVE B", "INDU C", "BURE"}
    assert weights["INVE B"] == pytest.approx(83.2, abs=0.5)
    assert sum(weights.values()) == pytest.approx(100.0)


def test_foreign_listing_is_converted_to_sek(fake_yf: dict[str, Any]) -> None:
    fake_yf["quotes"].update(
        {
            "BURE.ST": {"market_cap": 110e9, "currency": "SEK"},
            "SON.LS": {"market_cap": 10e9, "currency": "EUR"},
            "EURSEK=X": {"last_price": 11.0},
        }
    )

    weights = fetch_market_cap_weights([_product("BURE"), _product("SON")])

    # 10bn EUR at 11.00 is 110bn SEK — the same size as BURE, so 50/50.
    assert weights["SON"] == pytest.approx(50.0)
    assert weights["BURE"] == pytest.approx(50.0)


def test_company_without_market_cap_is_skipped_not_zero_weighted(
    fake_yf: dict[str, Any],
) -> None:
    fake_yf["quotes"].update(
        {
            "A.ST": {"market_cap": 100e9, "currency": "SEK"},
            "B.ST": {"market_cap": None, "currency": "SEK"},
        }
    )

    weights = fetch_market_cap_weights([_product("A"), _product("B")])

    assert weights == {"A": pytest.approx(100.0)}


def test_no_market_caps_yields_no_weights(fake_yf: dict[str, Any]) -> None:
    assert fetch_market_cap_weights([_product("A")]) == {}
