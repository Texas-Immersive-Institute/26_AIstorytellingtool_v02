"""Match scores: how closely a chat message's meaning fits a choice option or an influence prompt.

Two matchers share one interface:
- EmbeddingMatcher: a local sentence-embedding model, so "go inside" can match "Let him in".
  It also keeps the word-overlap score and uses whichever is higher.
- LexicalMatcher: word overlap only; used until the embedding model is downloaded.
"""

from __future__ import annotations

import re
from typing import Protocol

STOPWORDS = set(
    "a an the and or but if of to in on at for with by from up down out over is are was were be "
    "been am do does did i you he she it we they me him her us them my your his its our their "
    "this that these those so just very really please let's should would could can will shall "
    "not no yes go don didn won isn aren wasn m ll ve re d t s".split()
)
_WORD = re.compile(r"[a-z0-9']+")


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> set[str]:
    # Drop contraction endings ("he's" -> "he", "don't" -> "don"), then stem.
    words = (_stem(w.split("'")[0]) for w in _WORD.findall(text.lower()))
    return {w for w in words if w and w not in STOPWORDS}


class Matcher(Protocol):
    name: str

    def scores(self, message: str, candidates: list[str]) -> list[float]:
        """One score in 0..1 per candidate."""
        ...


class LexicalMatcher:
    name = "word overlap"

    """Content words the message shares with the candidate, divided by min(2, the message's
    content words) and capped at 1. Two shared words is a full match, so a long message isn't
    penalised for its filler.
    """

    def scores(self, message: str, candidates: list[str]) -> list[float]:
        stripped = message.strip().lower().rstrip(".!")
        msg = tokens(message)
        out = []
        for i, cand in enumerate(candidates):
            if stripped in {str(i + 1), f"option {i + 1}"}:
                out.append(1.0)
                continue
            cand_tokens = tokens(cand)
            if not msg or not cand_tokens:
                out.append(0.0)
                continue
            out.append(round(min(1.0, len(msg & cand_tokens) / min(len(msg), 2)), 3))
        return out


# Cosine similarity from small embedding models rarely drops below ~0.4 even for unrelated
# text, so it is rescaled: at or below LOW scores 0, at or above HIGH scores 1.
# Not yet tuned against real chat; the Debug view's threshold slider covers the gap.
SEMANTIC_LOW = 0.50
SEMANTIC_HIGH = 0.85
CACHE_SIZE = 4000


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingMatcher:
    name = "embeddings"

    def __init__(self, model: Embedder, low: float = SEMANTIC_LOW, high: float = SEMANTIC_HIGH):
        self.model = model
        self.low, self.high = low, high
        self.lexical = LexicalMatcher()
        self._cache: dict[str, list[float]] = {}

    def _vectors(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            if len(self._cache) > CACHE_SIZE:
                self._cache.clear()
            self._cache.update(zip(missing, self.model.embed(missing), strict=True))
        return [self._cache[t] for t in texts]

    def scores(self, message: str, candidates: list[str]) -> list[float]:
        lexical = self.lexical.scores(message, candidates)
        if not message.strip() or not candidates:
            return lexical
        msg, *cands = self._vectors([message, *candidates])
        out = []
        for lex, cand in zip(lexical, cands, strict=True):
            cos = sum(a * b for a, b in zip(msg, cand, strict=True))
            semantic = min(1.0, max(0.0, (cos - self.low) / (self.high - self.low)))
            out.append(round(max(lex, semantic), 3))
        return out
