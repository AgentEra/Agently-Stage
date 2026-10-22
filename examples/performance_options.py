"""Model-free infrastructure example: explicit ownership and capacity choices."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from agently_stage import Stage, Tunnel


async def main() -> None:
    async with Stage() as stage:

        async def batch() -> list[int]:
            tasks = [stage.create_task(asyncio.sleep(0, result=i * 2), origin="batch item") for i in range(4)]
            try:
                return await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

        print("batch:", await stage.go(batch).async_get())

    tunnel: Tunnel[int] = Tunnel(timeout=None, wake_mode="grouped")

    async def read() -> list[int]:
        return [value async for value in tunnel]

    readers = [asyncio.create_task(read()) for _ in range(8)]
    await asyncio.sleep(0)
    await asyncio.to_thread(tunnel.put, 42)
    tunnel.close()
    print("readers:", await asyncio.gather(*readers))

    with ThreadPoolExecutor(3) as slow_pool, ThreadPoolExecutor(1) as fast_pool:
        async with Stage(executor=slow_pool) as slow, Stage(executor=fast_pool) as fast:
            a, b = slow.go(pow, 2, 3), fast.go(pow, 3, 2)
            print("isolated:", await a.async_get(), await b.async_get())
        print("borrowed pool remains open:", fast_pool.submit(pow, 2, 4).result())


if __name__ == "__main__":
    asyncio.run(main())

# Expected key output from a real local run:
# batch: [0, 2, 4, 6]
# readers: [[42], [42], [42], [42], [42], [42], [42], [42]]
# isolated: 8 9
# borrowed pool remains open: 16
