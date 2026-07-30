from __future__ import annotations

import asyncio

import pytest

from agently_stage import LocalTaskScope


def test_local_task_scope_is_a_deprecated_stage_compatibility_shim() -> None:
    async def run() -> None:
        with pytest.warns(DeprecationWarning, match="Stage"):
            scope = LocalTaskScope()

        task = scope.spawn(asyncio.sleep(0, result="done"), origin="legacy")
        assert await task == "done"
        await scope.close(timeout=1)

        assert scope.pending_count == 0
        assert not hasattr(scope, "_tasks")
        assert not hasattr(scope, "_adopted")
        assert not hasattr(scope, "_origins")

    asyncio.run(run())
