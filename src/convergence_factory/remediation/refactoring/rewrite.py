"""OpenRewrite Convergence Executor.

Translates STANDARDIZE and RETIRE convergence recommendations into
executable OpenRewrite recipes (rewrite.yml) to automatically refactor
Java services across repositories.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional


def generate_topic_standardization_recipe(recipe_name: str, old_value: str, new_value: str) -> str:
    """Generates an OpenRewrite recipe that standardizes string constants or YAML properties."""
    return f"""---
type: specs.openrewrite.org/v1beta/recipe
name: com.acme.convergence.{recipe_name}
displayName: Standardize on {new_value}
description: Automatically converges legacy {old_value} references to the canonical {new_value}.
recipeList:
  - org.openrewrite.text.ChangeText:
      toReplace: "{old_value}"
      replacement: "{new_value}"
  - org.openrewrite.yaml.ChangePropertyValue:
      propertyKey: "kafka.topic.order"
      newValue: "{new_value}"
      oldValue: "{old_value}"
"""


def generate_class_migration_recipe(recipe_name: str, old_class: str, new_class: str) -> str:
    """Generates an OpenRewrite recipe to migrate from a retired class to a standardized one."""
    return f"""---
type: specs.openrewrite.org/v1beta/recipe
name: com.acme.convergence.{recipe_name}
displayName: Migrate {old_class} to {new_class}
description: Replaces usages of retired class {old_class} with standardized {new_class}.
recipeList:
  - org.openrewrite.java.ChangeType:
      oldFullyQualifiedTypeName: "{old_class}"
      newFullyQualifiedTypeName: "{new_class}"
"""


def generate_all_rewrite_recipes(clusters: List[dict], out_dir: str) -> List[str]:
    """Generates rewrite.yml recipes for all actionable clusters."""
    os.makedirs(out_dir, exist_ok=True)
    generated_files = []

    for idx, c in enumerate(clusters, 1):
        play = c.get("play", "")
        if play not in ("STANDARDIZE", "RETIRE"):
            continue

        shared_resources = c.get("shared", [])
        for rtype, rid in shared_resources:
            if rtype == "KAFKA_TOPIC":
                clean_name = rid.replace(".", "_").replace("-", "_")
                recipe_content = generate_topic_standardization_recipe(
                    f"Standardize_{clean_name}",
                    old_value=rid,
                    new_value=f"canonical.{rid}"
                )
                recipe_path = os.path.join(out_dir, f"rewrite_topic_{clean_name}.yml")
                with open(recipe_path, "w") as f:
                    f.write(recipe_content)
                generated_files.append(recipe_path)

            elif rtype == "SQL_TABLE":
                clean_name = rid.replace(".", "_")
                recipe_content = generate_topic_standardization_recipe(
                    f"StandardizeTable_{clean_name}",
                    old_value=rid,
                    new_value=f"canonical_{rid}"
                )
                recipe_path = os.path.join(out_dir, f"rewrite_table_{clean_name}.yml")
                with open(recipe_path, "w") as f:
                    f.write(recipe_content)
                generated_files.append(recipe_path)

    # Generate convenience runner shell script
    runner_script = os.path.join(out_dir, "run_rewrite.sh")
    with open(runner_script, "w") as f:
        f.write("""#!/usr/bin/env bash
# Runs OpenRewrite recipes against a target Maven project
TARGET_REPO="$1"
RECIPE_FILE="$2"

if [ -z "$TARGET_REPO" ] || [ -z "$RECIPE_FILE" ]; then
    echo "Usage: ./run_rewrite.sh <path-to-target-repo> <path-to-recipe.yml>"
    exit 1
fi

echo "Applying OpenRewrite recipe $RECIPE_FILE on $TARGET_REPO..."
mvn -f "$TARGET_REPO/pom.xml" org.openrewrite.maven:rewrite-maven-plugin:run \
    -Drewrite.configLocation="$RECIPE_FILE"
""")
    os.chmod(runner_script, 0o755)
    generated_files.append(runner_script)
    return generated_files
