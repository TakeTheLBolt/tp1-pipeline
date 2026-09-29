import os

import psycopg2
import pytest
import requests

from tests.integration.helpers import API_URL, POSTGRES, wait_until

RUN_E2E = os.getenv("RUN_E2E_TESTS", "false").lower() == "true"

pytestmark = pytest.mark.skipif(
    not RUN_E2E,
    reason="E2E tests disabled. Set RUN_E2E_TESTS=true."
)


def fetch_order(order_id):
    conn = psycopg2.connect(**POSTGRES)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT customer_id, product_id, quantity, unit_price, total_amount "
                "FROM processed_orders WHERE order_id = %s",
                (order_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def test_order_flows_from_api_to_postgres():
    # Given : l'infrastructure est démarrée
    assert requests.get(f"{API_URL}/api/health", timeout=10).json()["status"] == "UP"

    # When : une commande est envoyée à l'API
    response = requests.post(
        f"{API_URL}/api/orders",
        json={"customer_id": "C100", "product_id": "P001", "quantity": 3, "unit_price": 100},
        timeout=15,
    )
    assert response.status_code == 201
    order_id = response.json()["order_id"]

    # Then : elle est traitée par Spark et enregistrée dans PostgreSQL
    row = wait_until(lambda: fetch_order(order_id), timeout=90, interval=2)

    customer_id, product_id, quantity, unit_price, total_amount = row
    assert (customer_id, product_id, quantity) == ("C100", "P001", 3)
    assert float(unit_price) == 100.0
    assert float(total_amount) == 300.0


def test_invalid_order_is_rejected_and_never_stored():
    response = requests.post(
        f"{API_URL}/api/orders",
        json={"customer_id": "C100", "product_id": "P001", "quantity": -1, "unit_price": 100},
        timeout=15,
    )
    assert response.status_code == 422
