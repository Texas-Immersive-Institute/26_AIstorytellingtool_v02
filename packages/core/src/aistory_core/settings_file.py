"""Load and save a Pydantic settings model as JSON in an app's data folder."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temp file and rename, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_model(path: Path, model: type[M]) -> M:
    if not path.exists():
        return model()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return model.model_validate(data)


def save_model(path: Path, value: BaseModel) -> None:
    write_text_atomic(path, value.model_dump_json(indent=2) + "\n")
