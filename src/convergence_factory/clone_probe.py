"""Code Clone Probe.

Detects Type 1 (exact copy-paste) and Type 2 (parameterized / renamed)
code clones across modules using tokenized source line hashing.
Emits ClonePair facts at tier HIGH to feed the convergence graph.
"""
from __future__ import annotations

from itertools import combinations
import os
import re
from typing import Dict, List, Set

from .plugins.base import read, walk_files
from .schema import ClonePair
from .store import Store

_COMMENT_RE = re.compile(r'#.*|//.*|/\*[\s\S]*?\*/')
_IDENT_RE = re.compile(r'\b[A-Za-z_][A-Za-z0-9_]*\b')


def _tokenize_file(path: str, normalize_idents: bool = False) -> Set[str]:
    """Extracts non-empty normalized line tokens from source file."""
    try:
        content = read(path)
    except Exception:
        return set()

    clean = _COMMENT_RE.sub('', content)
    lines = [line.strip() for line in clean.splitlines() if line.strip()]

    tokens = set()
    for line in lines:
        if normalize_idents:
            norm_line = _IDENT_RE.sub('ID', line)
            tokens.add(norm_line)
        else:
            tokens.add(line)
    return tokens


def _module_tokens(module_path: str, normalize_idents: bool = False) -> Set[str]:
    """Collects all tokens across a module's source files."""
    tokens = set()
    for f in walk_files(module_path, (".py", ".java", ".sql")):
        tokens.update(_tokenize_file(f, normalize_idents=normalize_idents))
    return tokens


def detect_clones(store: Store, threshold: float = 0.60) -> List[ClonePair]:
    """Detects Type 1 and Type 2 cross-module code clones."""
    modules = store.modules()
    if len(modules) < 2:
        return []

    # Cache tokens per module
    t1_map: Dict[str, Set[str]] = {}
    t2_map: Dict[str, Set[str]] = {}

    for m in modules:
        t1_map[m.id] = _module_tokens(m.path, normalize_idents=False)
        t2_map[m.id] = _module_tokens(m.path, normalize_idents=True)

    clones: List[ClonePair] = []

    for ma, mb in combinations(modules, 2):
        toks1_a, toks1_b = t1_map[ma.id], t1_map[mb.id]
        toks2_a, toks2_b = t2_map[ma.id], t2_map[mb.id]

        if not toks1_a or not toks1_b:
            continue

        # Type 1 similarity (exact)
        overlap1 = len(toks1_a & toks1_b)
        union1 = len(toks1_a | toks1_b)
        sim1 = overlap1 / union1 if union1 else 0.0

        # Type 2 similarity (parameterized)
        overlap2 = len(toks2_a & toks2_b)
        union2 = len(toks2_a | toks2_b)
        sim2 = overlap2 / union2 if union2 else 0.0

        if sim1 >= threshold:
            clones.append(ClonePair(
                module_a=ma.id, module_b=mb.id,
                clone_type=1, similarity=round(sim1, 3), tier="HIGH"
            ))
        elif sim2 >= threshold:
            clones.append(ClonePair(
                module_a=ma.id, module_b=mb.id,
                clone_type=2, similarity=round(sim2, 3), tier="HIGH"
            ))

    store.add_clones(clones)
    return clones
