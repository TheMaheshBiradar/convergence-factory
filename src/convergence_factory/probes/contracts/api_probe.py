"""API / contract probe — duplicate service surfaces.

Scans each module's repo for API contracts — OpenAPI (yaml/json), gRPC .proto,
and GraphQL SDL — and emits:
  * ApiSurface facts (the catalogue of what each service exposes), and
  * IntegrationFacts with direction SERVES on HTTP_ENDPOINT, so two services that
    expose the SAME operation cluster as a DUP_ENDPOINT in the convergence graph.

Runs after extraction and before graph build. Language-agnostic: it reads the
contract artifacts, not the code.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Tuple

from convergence_factory.core.schema import ApiSurface, IntegrationFact, Provenance
from convergence_factory.core.store import Store
from convergence_factory.probes.integration.base import read, walk_files

try:
    import yaml
    _YAML = True
except Exception:                       # pragma: no cover
    _YAML = False

_HTTP_METHODS = {"get", "post", "put", "delete", "patch"}
_PROTO_RPC = re.compile(r'service\s+(\w+)\s*\{([^}]*)\}', re.S)
_PROTO_METHOD = re.compile(r'\brpc\s+(\w+)\s*\(')
_GQL_BLOCK = re.compile(r'type\s+(Query|Mutation)\s*\{([^}]*)\}', re.S)
_GQL_FIELD = re.compile(r'^\s*(\w+)\s*[\(:]', re.M)


def _load_spec(path: str):
    text = read(path)
    try:
        if path.endswith(".json"):
            return json.loads(text)
        if _YAML:
            return yaml.safe_load(text)
    except Exception:
        return None
    return None


def _is_openapi(basename: str) -> bool:
    b = basename.lower()
    return b.startswith(("openapi", "swagger")) and b.endswith((".yaml", ".yml", ".json"))


def _module_surfaces(module) -> Tuple[List[ApiSurface], List[IntegrationFact]]:
    apis: List[ApiSurface] = []
    facts: List[IntegrationFact] = []

    def serve(signature: str, kind: str, endpoint: str, rel: str):
        apis.append(ApiSurface(module_id=module.id, kind=kind, signature=signature,
                               role="server", tier="HIGH"))
        facts.append(IntegrationFact(
            module_id=module.id, direction="SERVES", resource_type="HTTP_ENDPOINT",
            resource_id=endpoint, tier="HIGH", provenance=Provenance(file=rel, snippet=signature)))

    # OpenAPI
    for f in walk_files(module.path, (".yaml", ".yml", ".json")):
        if not _is_openapi(os.path.basename(f)):
            continue
        spec = _load_spec(f)
        if not isinstance(spec, dict):
            continue
        rel = os.path.relpath(f, module.path)
        for path, item in (spec.get("paths") or {}).items():
            if not isinstance(item, dict):
                continue
            for method, _op in item.items():
                if method.lower() in _HTTP_METHODS:
                    sig = f"{method.upper()} {path}"
                    serve(sig, "REST", sig, rel)

    # gRPC
    for f in walk_files(module.path, (".proto",)):
        text = read(f)
        rel = os.path.relpath(f, module.path)
        for svc, body in _PROTO_RPC.findall(text):
            for rpc in _PROTO_METHOD.findall(body):
                serve(f"{svc}/{rpc}", "GRPC", f"grpc:{svc}/{rpc}", rel)

    # GraphQL
    for f in walk_files(module.path, (".graphql", ".graphqls", ".gql")):
        text = read(f)
        rel = os.path.relpath(f, module.path)
        for root, body in _GQL_BLOCK.findall(text):
            for field in _GQL_FIELD.findall(body):
                serve(f"{root}.{field}", "GRAPHQL", f"graphql:{root}.{field}", rel)

    return apis, facts


def extract_api(store: Store) -> int:
    """Scan all modules, write ApiSurface + SERVES facts. Returns endpoints found."""
    total = 0
    for m in store.modules():
        apis, facts = _module_surfaces(m)
        if apis:
            store.add_api(apis)
        if facts:
            store.add_integration(facts)
            total += len(facts)
    return total
