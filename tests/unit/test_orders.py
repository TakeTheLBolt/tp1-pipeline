import json
import re
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.main import Order, app, build_order_event, create_kafka_producer


def make_order(**overrides):
    data = {
        "customer_id": "C001",
        "product_id": "P001",
        "quantity": 1,
        "unit_price": 10.0,
    }
    data.update(overrides)
    return Order(**data)


def test_order_total():
    order = Order(
        customer_id="C001",
        product_id="P001",
        quantity=2,
        unit_price=50.0,
    )
    event = build_order_event(order)
    assert event["total_amount"] == 100.0


def test_order_contains_order_id():
    order = Order(
        customer_id="C001",
        product_id="P001",
        quantity=1,
        unit_price=10.0,
    )
    event = build_order_event(order)
    assert event["order_id"].startswith("ORD-")


def test_quantity_must_be_positive():
    with pytest.raises(Exception):
        Order(
            customer_id="C001",
            product_id="P001",
            quantity=0,
            unit_price=10.0,
        )


def test_invalid_fields_are_rejected():
    invalid = [
        {"quantity": -1},
        {"quantity": 1001},
        {"quantity": 1.5},
        {"unit_price": 0},
        {"unit_price": -5},
        {"unit_price": "abc"},
        {"customer_id": "C"},
        {"product_id": ""},
    ]
    for overrides in invalid:
        with pytest.raises(ValidationError):
            make_order(**overrides)


def test_boundary_values_are_accepted_and_total_is_rounded():
    order = make_order(customer_id="C1", product_id="P1", quantity=1000, unit_price=100000)
    assert build_order_event(order)["total_amount"] == 100000000.0
    assert build_order_event(make_order(quantity=3, unit_price=0.1))["total_amount"] == 0.3


def test_order_id_format_and_uniqueness():
    order = make_order()
    ids = [build_order_event(order)["order_id"] for _ in range(100)]
    assert all(re.fullmatch(r"ORD-[0-9A-F]{10}", i) for i in ids)
    assert len(set(ids)) == 100


def test_event_structure():
    event = build_order_event(
        make_order(customer_id="C100", product_id="P002", quantity=3, unit_price=100)
    )
    assert set(event) == {
        "order_id", "customer_id", "product_id",
        "quantity", "unit_price", "total_amount", "timestamp",
    }
    assert (event["customer_id"], event["product_id"], event["quantity"]) == ("C100", "P002", 3)
    assert event["total_amount"] == 300
    assert datetime.fromisoformat(event["timestamp"]).utcoffset() == timezone.utc.utcoffset(None)
    assert json.loads(json.dumps(event)) == event


def test_create_kafka_producer_configuration():
    with patch("app.main.KafkaProducer") as producer_cls:
        producer = create_kafka_producer()

    assert producer is producer_cls.return_value
    kwargs = producer_cls.call_args.kwargs
    assert kwargs["bootstrap_servers"] == main.KAFKA_BOOTSTRAP_SERVERS
    assert kwargs["retries"] == 5
    assert json.loads(kwargs["value_serializer"]({"a": 1})) == {"a": 1}


def test_health_and_products_endpoints():
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "UP", "service": "sales-api"}
    products = client.get("/api/products").json()
    assert {p["product_id"] for p in products} == {"P001", "P002", "P003", "P004"}


def test_create_order_endpoint_publishes_and_rejects_invalid():
    client = TestClient(app)
    payload = {"customer_id": "C100", "product_id": "P001", "quantity": 3, "unit_price": 100}

    with patch("app.main.create_kafka_producer") as factory:
        producer = factory.return_value

        response = client.post("/api/orders", json=payload)
        assert response.status_code == 201
        assert response.json()["total_amount"] == 300
        producer.send.assert_called_once()
        assert producer.send.call_args.args[0] == main.KAFKA_TOPIC
        producer.close.assert_called_once()

        producer.send.reset_mock()
        unknown = client.post("/api/orders", json={**payload, "product_id": "P999"})
        invalid = client.post("/api/orders", json={**payload, "quantity": 0})
        assert unknown.status_code == 404
        assert invalid.status_code == 422
        producer.send.assert_not_called()
