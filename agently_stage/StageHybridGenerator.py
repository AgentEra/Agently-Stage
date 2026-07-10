from __future__ import annotations

from typing import TypeVar

from .StageStream import StageStream

T = TypeVar("T")


class StageHybridGenerator(StageStream[T]):
    """Compatibility name for the canonical StageStream contract."""
