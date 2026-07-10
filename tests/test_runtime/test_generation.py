from __future__ import annotations

import time

from agently_stage import Stage, StageHandle
from agently_stage._runtime import _runtime_snapshot


def _wait_for_idle(timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _runtime_snapshot().active_generation_id is None:
            return True
        time.sleep(0.001)
    return False


def test_stage_creation_is_lazy() -> None:
    before = _runtime_snapshot()

    stage = Stage()

    assert _runtime_snapshot() == before
    stage.close()


def test_plain_stage_can_cross_finite_generations() -> None:
    stage = Stage()

    first = stage.go(lambda: 1)

    assert isinstance(first, StageHandle)
    assert first.get() == 1
    first.wait_settled()
    assert _wait_for_idle()

    second = stage.go(lambda: 2)

    assert second.get() == 2
    second.wait_settled()
    assert second.generation_id > first.generation_id
    assert _wait_for_idle()
    stage.close()
