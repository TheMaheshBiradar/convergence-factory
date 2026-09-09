"""HTTP API endpoints for order management."""
from models import Order
from service import create_order


def handle_checkout(payload: dict, producer, conn) -> None:
    order = Order(id=payload["id"], customer_id=payload["customer_id"], total=100.0)
    create_order(producer, order, conn)
