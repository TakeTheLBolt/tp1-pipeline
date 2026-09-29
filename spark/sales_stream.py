import os

import psycopg2
import psycopg2.extras
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType,
    DoubleType, TimestampType
)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sales.orders")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "sales")
POSTGRES_USER = os.getenv("POSTGRES_USER", "sales")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "sales")

spark = (
    SparkSession.builder
    .appName("SalesStreamingPipeline")
    .getOrCreate()
)

schema = StructType([
    StructField("order_id", StringType(), False),
    StructField("customer_id", StringType(), False),
    StructField("product_id", StringType(), False),
    StructField("quantity", IntegerType(), False),
    StructField("unit_price", DoubleType(), False),
    StructField("total_amount", DoubleType(), False),
    StructField("timestamp", TimestampType(), False),
])

raw = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
    .option("subscribe", KAFKA_TOPIC)
    .option("startingOffsets", "earliest")
    .load()
)

orders = (
    raw.select(
        from_json(col("value").cast("string"), schema).alias("data")
    )
    .select("data.*")
    .filter((col("quantity") > 0) & (col("unit_price") > 0))
)


def write_to_postgres(batch_df, batch_id):
    rows = [
        (
            r.order_id, r.customer_id, r.product_id, r.quantity,
            r.unit_price, r.total_amount, r.timestamp,
        )
        for r in batch_df.collect()
    ]
    if not rows:
        return

    # Insertion idempotente : un rejeu du topic (checkpoint perdu, redémarrage)
    # ne doit pas faire échouer le streaming sur la clé primaire order_id.
    conn = psycopg2.connect(
        host=POSTGRES_HOST, dbname=POSTGRES_DB,
        user=POSTGRES_USER, password=POSTGRES_PASSWORD,
    )
    try:
        with conn, conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO processed_orders "
                "(order_id, customer_id, product_id, quantity, unit_price, "
                "total_amount, event_timestamp) VALUES %s "
                "ON CONFLICT (order_id) DO NOTHING",
                rows,
            )
    finally:
        conn.close()


query = (
    orders.writeStream
    .foreachBatch(write_to_postgres)
    .outputMode("append")
    .option("checkpointLocation", "/tmp/sales-checkpoint")
    .start()
)

query.awaitTermination()
