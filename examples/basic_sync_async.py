from __future__ import annotations

import asyncio

from agently_stage import Stage

# Expected key output from a real local run:
# sync_result=42
# async_result=ready
# concurrent_results=['first', 'second']


async def async_task() -> str:
    await asyncio.sleep(0)
    return "ready"


async def concurrent_pair() -> list[str]:
    async def worker(name: str) -> str:
        await asyncio.sleep(0)
        return name

    return list(await asyncio.gather(worker("first"), worker("second")))


async def main() -> None:
    stage = Stage()
    sync_handle = stage.go(lambda: 6 * 7)
    async_handle = stage.go(async_task)
    concurrent_handle = stage.go(concurrent_pair)

    sync_result = await sync_handle.async_get()
    async_result = await async_handle.async_get()
    concurrent_results = await concurrent_handle.async_get()
    await stage.async_close()

    print(f"sync_result={sync_result}")
    print(f"async_result={async_result}")
    print(f"concurrent_results={concurrent_results}")


if __name__ == "__main__":
    asyncio.run(main())
