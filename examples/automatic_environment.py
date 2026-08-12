from __future__ import annotations

import asyncio

from agently_stage import Stage

# Expected key output from a real local run:
# sync adapter: user-7
# async adapter: 42
# sync context in async caller: user-8


async def fetch_name(identifier: int) -> str:
    await asyncio.sleep(0)
    return f"user-{identifier}"


def calculate(value: int) -> int:
    return value * 2


async def main() -> None:
    fetch_name_sync = Stage.as_sync(fetch_name)
    calculate_async = Stage.as_async(calculate)

    # A deliberate sync view works even though this caller already has a loop.
    print("sync adapter:", fetch_name_sync(7))
    print("async adapter:", await calculate_async(21))

    # The sync context also selects a carrier rather than blocking its own work.
    with Stage() as stage:
        print("sync context in async caller:", stage.get(fetch_name, 8))


if __name__ == "__main__":
    Stage.set_settings("runtime.carrier_loop_count", 1)
    asyncio.run(main())
