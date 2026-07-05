from scraper.main import to_yahoo_ticker


def test_nasdaq_ticker_gets_st_suffix() -> None:
    assert to_yahoo_ticker("BURE") == "BURE.ST"


def test_spaces_become_dashes() -> None:
    assert to_yahoo_ticker("INVE B") == "INVE-B.ST"


def test_override_for_foreign_listing() -> None:
    assert to_yahoo_ticker("SON") == "SON.LS"
