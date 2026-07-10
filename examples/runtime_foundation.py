from __future__ import annotations

import asyncio
import threading

from agently_stage import EventEmitter, Stage

# Expected key output from a real local run:
# body=ready
# drained=True
# stream=[0, 1, 2]
# listener_calls=1


def main() -> None:
    drained = threading.Event()

    async def request() -> str:
        async def background_cleanup() -> None:
            await asyncio.sleep(0.02)
            drained.set()

        asyncio.create_task(background_cleanup())
        return "ready"

    request_stage = Stage()
    request_handle = request_stage.go(request)
    body = request_handle.get()
    request_handle.wait_settled()
    request_stage.close()

    def source():
        yield from range(3)

    stream_stage = Stage()
    stream = stream_stage.go(source)
    stream_values = stream.get()
    stream_stage.close()

    listener_calls = 0
    emitter = EventEmitter()

    @emitter.once("ready")
    def listener() -> None:
        nonlocal listener_calls
        listener_calls += 1

    emitter.emit("ready", wait=True)
    emitter.emit("ready", wait=True)

    print(f"body={body}")
    print(f"drained={drained.is_set()}")
    print(f"stream={stream_values}")
    print(f"listener_calls={listener_calls}")


if __name__ == "__main__":
    main()
