"""Domain models for order management."""
from dataclasses import dataclass


@dataclass
class Order:
    id: str
    customer_id: str
    total: float
