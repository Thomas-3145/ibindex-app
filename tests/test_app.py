from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from shared.models import HoldingRow, SnapshotRow


def test_app_renders_whole_share_portfolio_with_cash(
    sample_snapshots: list[SnapshotRow], sample_holdings: list[HoldingRow]
) -> None:
    with (
        patch(
            "shared.db.get_latest_run",
            return_value=(1, sample_snapshots[0].scraped_at),
        ),
        patch("shared.db.get_snapshots", return_value=sample_snapshots),
        patch("shared.db.get_holdings", return_value=sample_holdings),
    ):
        app = AppTest.from_file("app/main.py").run(timeout=15)

    assert not app.exception
    assert [metric.label for metric in app.metric] == ["Investerat", "Kvar i kassa"]
    assert [metric.value for metric in app.metric] == ["99,950 SEK", "50 SEK"]

    portfolio = app.dataframe[0].value
    assert portfolio.iloc[-1]["Bolag"] == "Kassa"
    assert portfolio.iloc[-1]["Investerat (SEK)"] == "50.00"
    assert all(value != "—" for value in portfolio.iloc[:-1]["Antal aktier"])
