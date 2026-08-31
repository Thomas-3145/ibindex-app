from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from shared.models import HoldingRow, ShareClassRow, SnapshotRow


def _table_with(app: AppTest, column: str) -> pd.DataFrame:
    """Pick a rendered table by its columns — order shifts as sections are added."""
    return next(df.value for df in app.dataframe if column in df.value.columns)


@contextmanager
def _stubbed_db(
    snapshots: list[SnapshotRow],
    holdings: list[HoldingRow],
    share_classes: list[ShareClassRow],
) -> Iterator[None]:
    with (
        patch("shared.db.get_latest_run", return_value=(1, snapshots[0].scraped_at)),
        patch("shared.db.get_snapshots", return_value=snapshots),
        patch("shared.db.get_holdings", return_value=holdings),
        patch("shared.db.get_share_classes", return_value=share_classes),
    ):
        yield


def test_app_renders_whole_share_portfolio_with_cash(
    sample_snapshots: list[SnapshotRow],
    sample_holdings: list[HoldingRow],
    sample_share_classes: list[ShareClassRow],
) -> None:
    with _stubbed_db(sample_snapshots, sample_holdings, sample_share_classes):
        app = AppTest.from_file("app/main.py").run(timeout=15)

    assert not app.exception
    assert [metric.label for metric in app.metric] == ["Investerat", "Kvar i kassa"]
    assert [metric.value for metric in app.metric] == ["99,950 SEK", "50 SEK"]

    portfolio = _table_with(app, "Antal aktier")
    assert portfolio.iloc[-1]["Bolag"] == "Kassa"
    assert portfolio.iloc[-1]["Investerat (SEK)"] == "50.00"
    assert all(value != "—" for value in portfolio.iloc[:-1]["Antal aktier"])


def test_app_offers_a_share_class_choice(
    sample_snapshots: list[SnapshotRow],
    sample_holdings: list[HoldingRow],
    sample_share_classes: list[ShareClassRow],
) -> None:
    with _stubbed_db(sample_snapshots, sample_holdings, sample_share_classes):
        app = AppTest.from_file("app/main.py").run(timeout=15)

    assert not app.exception
    assert "Aktieslag" in [radio.label for radio in app.sidebar.radio]


def test_app_hides_share_class_choice_without_data(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:
    with _stubbed_db(sample_snapshots, sample_holdings, []):
        app = AppTest.from_file("app/main.py").run(timeout=15)

    assert not app.exception
    assert "Aktieslag" not in [radio.label for radio in app.sidebar.radio]


def test_app_buys_the_cheaper_class_when_asked(
    sample_snapshots: list[SnapshotRow],
    sample_holdings: list[HoldingRow],
    sample_share_classes: list[ShareClassRow],
) -> None:
    with _stubbed_db(sample_snapshots, sample_holdings, sample_share_classes):
        app = AppTest.from_file("app/main.py").run(timeout=15)
        class_mode = next(r for r in app.sidebar.radio if r.label == "Aktieslag")
        app = class_mode.set_value("Billigaste").run(timeout=15)

    assert not app.exception
    portfolio = _table_with(app, "Antal aktier")
    investor = portfolio[portfolio["Bolag"] == "Investor A"]
    assert len(investor) == 1
    assert investor.iloc[0]["Ticker"] == "INVE A"
    assert investor.iloc[0]["Pris (SEK)"] == "285.00"
    # KINV A is cheaper but barely traded, so Kinnevik stays on its B class.
    assert (portfolio["Bolag"] == "Kinnevik B").any()
