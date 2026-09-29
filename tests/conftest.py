"""Shared pytest configuration."""
import os

import pytest


@pytest.fixture
def client():
    """Live NHL/ESPN client for tests/test_data_gathering.py.

    Those checks call real APIs and clear_old_cache(), which deletes cache
    files, so they only run when RUN_LIVE_TESTS=1 is set.
    """
    if os.environ.get("RUN_LIVE_TESTS") != "1":
        pytest.skip("live API checks; set RUN_LIVE_TESTS=1 to run")
    from src.api.nhl_client import NHLClient

    return NHLClient()
