from __future__ import annotations

import asyncio
import threading

from agently_stage import Stage

# Expected key output from a real local run:
# body=ready
# settled_before_wait=False
# settled_after_wait=True


def main() -> None:
    child_started = threading.Event()
    release_child = threading.Event()
    background_finished = threading.Event()

    async def request() -> str:
        async def background_cleanup() -> None:
            child_started.set()
            await asyncio.to_thread(release_child.wait)
            background_finished.set()

        asyncio.create_task(background_cleanup())
        while not child_started.is_set():
            await asyncio.sleep(0)
        return "ready"

    stage = Stage()
    handle = stage.go(request)
    body = handle.get()
    settled_before_wait = background_finished.is_set()
    release_child.set()
    handle.wait_settled()
    settled_after_wait = background_finished.is_set()
    stage.close()

    print(f"body={body}")
    print(f"settled_before_wait={settled_before_wait}")
    print(f"settled_after_wait={settled_after_wait}")


if __name__ == "__main__":
    main()
