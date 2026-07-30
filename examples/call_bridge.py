from __future__ import annotations

import asyncio
import threading

from agently_stage import StageCallBridge

# Expected key output from a real local run:
# user-7
# 0
# source settled

source_settled = threading.Event()


async def async_source():
    try:
        for item in range(3):
            await asyncio.sleep(0)
            yield item
    finally:
        source_settled.set()


def main() -> None:
    bridge = StageCallBridge()

    async def fetch(identifier: int) -> str:
        await asyncio.sleep(0)
        return f"user-{identifier}"

    print(bridge.as_sync(fetch)(7))

    stream = bridge.iter_sync(async_source())
    print(next(stream))
    stream.close()
    assert source_settled.is_set()
    print("source settled")

    # Scheduling owners can opt into settlement-aware cancellation explicitly.
    managed_fetch = bridge.as_sync(fetch, managed=True)
    assert managed_fetch(8) == "user-8"
    bridge.close()


if __name__ == "__main__":
    main()
