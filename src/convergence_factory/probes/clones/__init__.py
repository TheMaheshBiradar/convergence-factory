"""Code Clone Detection Probe (Probe 5).

Tokenized AST hashing detecting Type-1 (exact copy-paste) and Type-2 (renamed/parameterized) clones.
"""
from . import clone_probe
from .clone_probe import detect_clones

__all__ = ["clone_probe", "detect_clones"]
