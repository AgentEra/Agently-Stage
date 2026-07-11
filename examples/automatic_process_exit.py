from __future__ import annotations

import asyncio
import threading

from agently_stage import Stage

# Expected key output from a real local run:
# body=ready
# background_finished=True


def main() -> None:
    child_started = threading.Event()
    body_printed = threading.Event()

    async def request() -> str:
        async def background_cleanup() -> None:
            child_started.set()
            await asyncio.to_thread(body_printed.wait)
            print("background_finished=True")

        asyncio.create_task(background_cleanup())
        while not child_started.is_set():
            await asyncio.sleep(0)
        return "ready"

    handle = Stage().go(request)
    print(f"body={handle.get()}")
    body_printed.set()


if __name__ == "__main__":
    main()
