import os

import pytest
import requests

from tests.integration.helpers import API_URL

RUN_INTEGRATION = os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"

pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true."
)


def test_health():
    response = requests.get(f"{API_URL}/api/health", timeout=10)
    assert response.status_code == 200
    assert response.json()["status"] == "UP"
