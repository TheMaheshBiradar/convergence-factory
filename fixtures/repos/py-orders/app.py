"""Orders service (team-orders). Publishes order events and persists customers."""
import os

from kafka import KafkaProducer
import psycopg2

ORDER_TOPIC = "order.created"          # literal constant -> resolves HIGH


def publish(producer, order):
    producer.send(ORDER_TOPIC, value=order)


def save_customer(conn, cust):
    cur = conn.cursor()
    cur.execute("INSERT INTO customers (id, name) VALUES (%s, %s)", cust)
    conn.commit()
