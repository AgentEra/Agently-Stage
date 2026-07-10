from __future__ import annotations

import asyncio
import threading

from agently_stage import Stage

# Expected key output from a real local run:
# body=ready
# background_finished=True


def main() -> None:
    body_printed = threading.Event()

    async def request() -> str:
        async def background_cleanup() -> None:
            await asyncio.to_thread(body_printed.wait)
            print("background_finished=True")

        asyncio.create_task(background_cleanup())
        return "ready"

    handle = Stage().go(request)
    print(f"body={handle.get()}")
    body_printed.set()


if __name__ == "__main__":
    main()
