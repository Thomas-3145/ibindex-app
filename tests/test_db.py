"""Reads that have to survive a partially migrated database."""

from unittest.mock import patch

import psycopg
import pytest

from shared.db import get_share_classes


def test_missing_share_class_table_does_not_take_the_app_down() -> None:
    """The app image ships before the CronJob applies the new schema."""
    with patch("shared.db.get_connection", side_effect=psycopg.errors.UndefinedTable()):
        assert get_share_classes(1) == []


def test_other_database_errors_still_surface() -> None:
    """Degrading on a real outage would hide it behind an empty portfolio."""
    with (
        patch("shared.db.get_connection", side_effect=psycopg.OperationalError("down")),
        pytest.raises(psycopg.OperationalError),
    ):
        get_share_classes(1)
