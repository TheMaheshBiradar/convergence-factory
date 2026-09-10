"""Automated Refactoring & Migration Recipes (OpenRewrite)."""
from . import rewrite
from .rewrite import (
    generate_all_rewrite_recipes,
    generate_class_migration_recipe,
    generate_endpoint_standardization_recipe,
    generate_table_standardization_recipe,
    generate_topic_standardization_recipe,
)

__all__ = [
    "rewrite",
    "generate_all_rewrite_recipes",
    "generate_class_migration_recipe",
    "generate_endpoint_standardization_recipe",
    "generate_table_standardization_recipe",
    "generate_topic_standardization_recipe",
]
