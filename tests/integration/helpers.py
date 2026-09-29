import os
import time

API_URL = os.getenv("API_URL", "http://localhost:8000")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS_TEST", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sales.orders")
POSTGRES = {
    "host": os.getenv("POSTGRES_HOST_TEST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT_TEST", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "sales"),
    "user": os.getenv("POSTGRES_USER", "sales"),
    "password": os.getenv("POSTGRES_PASSWORD", "sales"),
}


def wait_until(fetch, timeout=60, interval=1):
    """Appelle fetch() jusqu'à obtenir une valeur non vide, sinon échoue au timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = fetch()
        if result:
            return result
        time.sleep(interval)
    raise AssertionError(f"Timeout après {timeout}s : résultat non disponible")
