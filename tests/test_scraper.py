import pytest

from scraper.main import HTTP, require_minimum_coverage, to_yahoo_ticker


def test_nasdaq_ticker_gets_st_suffix() -> None:
    assert to_yahoo_ticker("BURE") == "BURE.ST"


def test_spaces_become_dashes() -> None:
    assert to_yahoo_ticker("INVE B") == "INVE-B.ST"


def test_override_for_foreign_listing() -> None:
    assert to_yahoo_ticker("SON") == "SON.LS"


def test_http_session_retries_transient_get_and_post_failures() -> None:
    retry = HTTP.get_adapter("https://").max_retries

    assert retry.total == 3
    assert retry.allowed_methods is not None
    assert {"GET", "POST"}.issubset(retry.allowed_methods)
    assert {429, 500, 502, 503, 504}.issubset(retry.status_forcelist)


def test_minimum_coverage_accepts_half() -> None:
    require_minimum_coverage("Test data", successful=5, total=10)


def test_minimum_coverage_rejects_degraded_data() -> None:
    with pytest.raises(RuntimeError, match="4 of 10"):
        require_minimum_coverage("Test data", successful=4, total=10)


def test_minimum_coverage_rejects_empty_source() -> None:
    with pytest.raises(RuntimeError, match="no companies"):
        require_minimum_coverage("Test data", successful=0, total=0)
