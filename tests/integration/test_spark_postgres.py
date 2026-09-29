import json
import os
import uuid
from datetime import datetime, timezone

import psycopg2
import pytest
from kafka import KafkaProducer

from tests.integration.helpers import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC, POSTGRES, wait_until

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true",
    reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true.",
)


def test_kafka_event_is_processed_by_spark_into_postgres():
    order_id = f"IT-{uuid.uuid4().hex[:10].upper()}"
    event = {
        "order_id": order_id,
        "customer_id": "C300",
        "product_id": "P003",
        "quantity": 4,
        "unit_price": 25.0,
        "total_amount": 100.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    try:
        producer.send(KAFKA_TOPIC, value=event).get(timeout=10)
        producer.flush()
    finally:
        producer.close()

    conn = psycopg2.connect(**POSTGRES)
    conn.autocommit = True

    def fetch_row():
        with conn.cursor() as cur:
            cur.execute(
                "SELECT customer_id, product_id, quantity, unit_price, total_amount "
                "FROM processed_orders WHERE order_id = %s",
                (order_id,),
            )
            return cur.fetchone()

    try:
        row = wait_until(fetch_row, timeout=90, interval=2)
    finally:
        conn.close()

    customer_id, product_id, quantity, unit_price, total_amount = row
    assert (customer_id, product_id, quantity) == ("C300", "P003", 4)
    assert float(unit_price) == 25.0
    assert float(total_amount) == 100.0
