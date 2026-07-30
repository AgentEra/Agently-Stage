from __future__ import annotations

import asyncio

from agently_stage import StageCallBridge

# Expected key output from a real local run:
# user-7
# 0
# source settled


async def async_source():
    try:
        for item in range(3):
            await asyncio.sleep(0)
            yield item
    finally:
        print("source settled")


def main() -> None:
    bridge = StageCallBridge()

    async def fetch(identifier: int) -> str:
        await asyncio.sleep(0)
        return f"user-{identifier}"

    print(bridge.as_sync(fetch)(7))

    stream = bridge.iter_sync(async_source())
    print(next(stream))
    stream.close()

    # Scheduling owners can opt into settlement-aware cancellation explicitly.
    managed_fetch = bridge.as_sync(fetch, managed=True)
    assert managed_fetch(8) == "user-8"
    bridge.close()


if __name__ == "__main__":
    main()
