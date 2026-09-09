"""M1.5 — embeddings.

`Embedder` is the seam. In production you point `RestEmbedder` at a self-hosted
embedding model so all 200 private repos stay in-boundary. `HashingEmbedder` is a
deterministic, dependency-free stand-in so the pipeline runs anywhere and tests
are reproducible — it captures lexical overlap, enough to demonstrate recall,
without pretending to be a real code/text model.

Key design point (see the blueprint): we embed the language-neutral SUMMARY, not
raw code, so a Java and a Python module that do the same thing land near each
other instead of clustering by syntax.
"""
from __future__ import annotations

import hashlib
import math
from typing import List, Protocol


class Embedder(Protocol):
    def embed(self, text: str) -> List[float]: ...


class HashingEmbedder:
    """Char-n-gram hashing → L2-normalized vector. Deterministic across runs."""

    def __init__(self, dim: int = 256, n: int = 3):
        self.dim = dim
        self.n = n

    def embed(self, text: str) -> List[float]:
        text = " ".join((text or "").lower().split())
        vec = [0.0] * self.dim
        grams = [text[i:i + self.n] for i in range(max(0, len(text) - self.n + 1))]
        for g in grams or [text]:
            h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=4).digest(), "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


class RestEmbedder:
    """Production embedder: POST text to a self-hosted model, get a vector back.

    Left as a thin stub — wire it to your serving endpoint. The rest of the
    factory neither knows nor cares which Embedder is in use.
    """

    def __init__(self, url: str = ""):
        self.url = url

    def embed(self, text: str) -> List[float]:  # pragma: no cover
        raise NotImplementedError(
            "RestEmbedder is a stub. Point it at your self-hosted embedding model, "
            "or use HashingEmbedder for a local run.")


def cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))   # inputs are L2-normalized
