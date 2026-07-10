from __future__ import annotations

from .StageHandle import StageHandle

# The preview name remains import-compatible without preserving a second
# result lifecycle implementation.
StageResponse = StageHandle

__all__ = ["StageResponse"]
