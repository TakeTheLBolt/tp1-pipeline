import json
import os
import uuid

import pytest
import requests
from kafka import KafkaConsumer

from tests.integration.helpers import API_URL, KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC, wait_until

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true",
    reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true.",
)


def test_api_publishes_order_to_kafka():
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"it-{uuid.uuid4().hex}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=2000,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    try:
        response = requests.post(
            f"{API_URL}/api/orders",
            json={"customer_id": "C200", "product_id": "P002", "quantity": 2, "unit_price": 50},
            timeout=15,
        )
        assert response.status_code == 201
        order_id = response.json()["order_id"]

        def find_event():
            for message in consumer:
                if message.value["order_id"] == order_id:
                    return message.value
            return None

        event = wait_until(find_event, timeout=30)
    finally:
        consumer.close()

    assert event["customer_id"] == "C200"
    assert event["product_id"] == "P002"
    assert event["total_amount"] == 100
