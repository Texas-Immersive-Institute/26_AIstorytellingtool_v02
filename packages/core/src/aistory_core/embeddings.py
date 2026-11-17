"""A small local sentence-embedding model (fastembed, ONNX on the CPU; no GPU, no PyTorch).

The model is not bundled: it downloads once (about 67 MB) when the user asks for it, into the
app's data folder. Until then `status().ready` is False and callers fall back to something else.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_MODEL_MB = 67


class EmbeddingStatus(BaseModel):
    model: str
    ready: bool
    downloading: bool
    detail: str


class EmbeddingModel:
    def __init__(self, cache_dir: Path, model_name: str = DEFAULT_MODEL):
        self.cache_dir = cache_dir
        self.model_name = model_name
        self._model: Any = None
        self._lock = threading.Lock()
        self._downloading = False
        self._error: str | None = None
        self._checked = False

    def status(self) -> EmbeddingStatus:
        if not self._checked and self._model is None and not self._downloading:
            self.load(download=False)
        if self._model is not None:
            detail = f"{self.model_name} is loaded."
        elif self._downloading:
            detail = f"Downloading {self.model_name} (about {DEFAULT_MODEL_MB} MB)…"
        else:
            detail = self._error or f"{self.model_name} is not downloaded yet."
        return EmbeddingStatus(
            model=self.model_name,
            ready=self._model is not None,
            downloading=self._downloading,
            detail=detail,
        )

    def load(self, download: bool) -> bool:
        """Load from the cache, or download first if `download`. Safe to call from threads."""
        with self._lock:
            if self._model is not None:
                return True
            self._checked = True
            try:
                from fastembed import TextEmbedding  # imported lazily: it is slow to import
            except ImportError:
                self._error = "fastembed is not installed."
                return False
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._downloading = download
            try:
                self._model = TextEmbedding(
                    self.model_name, cache_dir=str(self.cache_dir), local_files_only=not download
                )
                self._error = None
            except Exception as exc:  # fastembed raises ValueError/OSError/network errors
                self._error = (
                    f"{self.model_name} is not downloaded yet."
                    if not download
                    else f"Download failed: {str(exc)[:200]}"
                )
                return False
            finally:
                self._downloading = False
            return True

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Unit-length vectors, one per text. Requires a loaded model."""
        if self._model is None:
            raise RuntimeError("The embedding model is not loaded.")
        out = []
        for vec in self._model.embed(texts):
            norm = float((vec**2).sum()) ** 0.5 or 1.0
            out.append([float(x) / norm for x in vec])
        return out


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
