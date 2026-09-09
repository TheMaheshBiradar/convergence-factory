"""Inventory sync (team-warehouse) — same team as svc-inventory, other language.
Publishes the identical event: a RETIRE-grade duplicate."""
from confluent_kafka import Producer

TOPIC = "inventory.updated"            # literal constant -> HIGH


def run(producer: Producer, event: bytes) -> None:
    producer.produce(TOPIC, event)
    producer.flush()
