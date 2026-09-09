"""Order service logic."""
from kafka import KafkaProducer
from models import Order

ORDER_TOPIC = "order.created"


def create_order(producer: KafkaProducer, order: Order, conn) -> None:
    producer.send(ORDER_TOPIC, value=order.id.encode("utf8"))
    cur = conn.cursor()
    cur.execute("INSERT INTO customers (id, name) VALUES (%s, %s)", (order.customer_id, "Customer"))
    conn.commit()
