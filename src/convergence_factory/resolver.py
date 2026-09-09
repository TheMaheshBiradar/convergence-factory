"""M5 — The config / constant resolver.

Kafka topics and SQL tables are almost never string literals at the call site —
they hide in constants, injected config keys, and YAML/properties files. The
integration probe is only as good as this resolver, so it is a first-class,
shared component with its own tiering:

    1. literal at the call site            -> HIGH
    2. local constant / final static       -> HIGH
    3. injected config key (yaml/env/props) -> MED
    4. computed / dynamic at runtime        -> UNRESOLVED (tracked as a gap)

`resolve()` returns a Resolution; callers turn an UNRESOLVED result into a Gap so
the coverage number stays honest about what could and could not be seen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ResolutionContext:
    """Everything the resolver can consult for one module."""
    constants: Dict[str, str] = field(default_factory=dict)   # NAME -> value
    config: Dict[str, str] = field(default_factory=dict)      # dotted.key -> value
    env: Dict[str, str] = field(default_factory=dict)         # ENV_VAR -> default


@dataclass
class Resolution:
    value: Optional[str]
    tier: str            # HIGH / MED / LOW
    notes: str = ""

    @property
    def resolved(self) -> bool:
        return self.value is not None


_LITERAL = re.compile(r'''^\s*["']([^"']+)["']\s*$''')
_CONFIG_KEY = re.compile(r'\$\{([^:}]+)(?::([^}]*))?\}')   # ${a.b.c:default}


def resolve(expr: str, ctx: ResolutionContext) -> Resolution:
    """Resolve a topic/table/url expression to a concrete string + a tier."""
    expr = (expr or "").strip()

    # 1. literal
    m = _LITERAL.match(expr)
    if m:
        return Resolution(m.group(1), "HIGH", "literal at call site")

    # 2. local constant (bare identifier, or an attribute like settings.TOPIC)
    ident = expr.split(".")[-1]
    if expr in ctx.constants:
        return Resolution(ctx.constants[expr], "HIGH", "local constant")
    if ident in ctx.constants:
        return Resolution(ctx.constants[ident], "HIGH", "local constant")

    # 3a. Spring-style placeholder: "${kafka.topic.order}" or ${...:default}
    m = _CONFIG_KEY.search(expr)
    if m:
        key, default = m.group(1), m.group(2)
        if key in ctx.config:
            return Resolution(ctx.config[key], "MED", f"config key {key}")
        if default:
            return Resolution(default, "MED", f"config default for {key}")

    # 3b. config key referenced directly (dotted) or env var default
    if expr in ctx.config:
        return Resolution(ctx.config[expr], "MED", f"config key {expr}")
    if ident in ctx.env:
        return Resolution(ctx.env[ident], "MED", f"env default {ident}")

    # 4. unresolved -> caller records a gap
    return Resolution(None, "LOW", "dynamic / unresolved")


def load_simple_yaml(text: str) -> Dict[str, str]:
    """Minimal indentation-based YAML → dotted keys.

    Handles the nested `key:\\n  sub: value` shape used by application.yml for
    topic/table config. Production swaps in a real YAML parser; this keeps the
    resolver dependency-free and the fixtures runnable.
    """
    out: Dict[str, str] = {}
    stack = []  # (indent, key)
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip().strip('"\'')
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if val:
            dotted = ".".join([k for _, k in stack] + [key])
            out[dotted] = val
        else:
            stack.append((indent, key))
    return out


def load_properties(text: str) -> Dict[str, str]:
    """key=value .properties → dict (dotted keys used as-is)."""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out
