"""Remediation, Governance & Refactoring Layer.

Contains:
- ratchets: One-Way CI/CD Ratchets (ArchUnit, Import-Linter, dependency-cruiser)
- refactoring: OpenRewrite Declarative Recipes
- healing: Automated Closed-Loop Self-Healing Engine
"""
from . import healing, ratchets, refactoring
from .healing import HealingAction, HealingReport, heal_cluster, run_self_healing
from .ratchets import (
    generate_all_ratchets,
    generate_archunit_rule,
    generate_dependency_cruiser_rule,
    generate_import_linter_contract,
)
from .refactoring import (
    generate_all_rewrite_recipes,
    generate_class_migration_recipe,
    generate_endpoint_standardization_recipe,
    generate_table_standardization_recipe,
    generate_topic_standardization_recipe,
)

__all__ = [
    "ratchets",
    "refactoring",
    "healing",
    "generate_all_ratchets",
    "generate_archunit_rule",
    "generate_dependency_cruiser_rule",
    "generate_import_linter_contract",
    "generate_all_rewrite_recipes",
    "generate_class_migration_recipe",
    "generate_endpoint_standardization_recipe",
    "generate_table_standardization_recipe",
    "generate_topic_standardization_recipe",
    "HealingAction",
    "HealingReport",
    "heal_cluster",
    "run_self_healing",
]
