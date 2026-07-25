from __future__ import annotations

import asyncio
import contextvars

from agently_stage import LocalTaskOutcome, LocalTaskScope

# Expected key output from a real local run:
# values=['caller', 'caller']
# origins=['event:first', 'flow:second']
# pending=0


async def main() -> None:
    marker = contextvars.ContextVar("local_task_scope_marker", default="missing")
    outcomes: list[LocalTaskOutcome] = []
    scope = LocalTaskScope(on_done=outcomes.append)

    async def read_context() -> str:
        await asyncio.sleep(0)
        return marker.get()

    token = marker.set("caller")
    try:
        first = scope.spawn(read_context(), origin="event:first")
        second = scope.spawn(read_context(), origin="flow:second")
    finally:
        marker.reset(token)

    values = await asyncio.gather(first, second)
    await scope.close(timeout=1)

    print(f"values={values}")
    print(f"origins={sorted(outcome.origin for outcome in outcomes)}")
    print(f"pending={scope.pending_count}")


if __name__ == "__main__":
    asyncio.run(main())
