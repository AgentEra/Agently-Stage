from __future__ import annotations

import asyncio
import threading

from agently_stage import EventEmitter

# Expected key output from a real local run:
# listener_results=['sync:ready', 'async:ready']
# once_calls=1
# wait_false_ready=False
# isolated_error=ValueError
# ordinary_close_required=False


def main() -> None:
    emitter = EventEmitter()

    def sync_listener(value: str) -> str:
        return f"sync:{value}"

    async def async_listener(value: str) -> str:
        await asyncio.sleep(0)
        return f"async:{value}"

    emitter.on("ready", sync_listener)
    emitter.on("ready", async_listener)
    listener_handles = emitter.emit("ready", "ready", wait=False)
    listener_results = [handle.get() for handle in listener_handles]
    for handle in listener_handles:
        handle.wait_settled()

    once_calls = 0

    @emitter.once("once")
    def once_listener() -> None:
        nonlocal once_calls
        once_calls += 1

    emitter.emit("once", wait=True)
    emitter.emit("once", wait=True)

    slow_started = threading.Event()
    release_slow = threading.Event()

    @emitter.on("slow")
    def slow_listener() -> str:
        slow_started.set()
        release_slow.wait()
        return "slow:done"

    slow_handle = emitter.emit("slow", wait=False)[0]
    assert slow_started.wait(timeout=1)
    wait_false_ready = slow_handle.is_ready()
    release_slow.set()
    slow_handle.get()
    slow_handle.wait_settled()

    @emitter.on("failure")
    def failing_listener() -> None:
        raise ValueError("listener failed")

    failure_handle = emitter.emit("failure", wait=False)[0]
    try:
        failure_handle.get()
    except ValueError as error:
        isolated_error = type(error).__name__
    failure_handle.wait_settled()

    print(f"listener_results={listener_results}")
    print(f"once_calls={once_calls}")
    print(f"wait_false_ready={wait_false_ready}")
    print(f"isolated_error={isolated_error}")
    print("ordinary_close_required=False")


if __name__ == "__main__":
    main()
