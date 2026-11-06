"""Synthetic negative cases; these are not fixtures captured from a grandMA2."""
import pytest

from ma2panel.commands import parse_running


@pytest.mark.parametrize("rows", [
    "Executor 1.101 Piano  Running Off",
    "Executor 1.101 Piano  Off  Active",
    "Executor 1.101 Piano  Running\nExecutor 1.101 Piano  Off",
    "Executor 1.101 Piano  Off\nExecutor 1.101 Piano  Running",
    "Executor 1.101 Piano  Off\nExecutor 1.101 Piano  Unknown",
    "Executor 1.101 Piano  Unknown\nExecutor 1.101 Piano  Off",
])
def test_ambiguous_executor_never_becomes_known_on_or_off(rows):
    assert parse_running(rows + "\nExecutor 1.102 Other  Off") == {"1.102": False}


@pytest.mark.parametrize("status,expected", [("Running", True), ("Off", False)])
def test_consistent_duplicate_status_is_order_independent(status, expected):
    row = f"Executor 1.101 Piano  {status}"
    assert parse_running(row + "\n" + row) == {"1.101": expected}
