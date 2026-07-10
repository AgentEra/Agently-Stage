from __future__ import annotations

import asyncio
import threading

from agently_stage import Stage, StageStream

# Expected key output from a real local run:
# started_before_read=False
# lazy_result=[0, 1, 2]
# sync_replay=[0, 1, 2]
# async_replay=[0, 1, 2]
# failure_values=[3]
# failure_type=ValueError


async def collect_async(stream: StageStream[int]) -> list[int]:
    return [item async for item in stream]


def main() -> None:
    source_started = threading.Event()

    async def source():
        source_started.set()
        for item in range(3):
            await asyncio.sleep(0)
            yield item

    stage = Stage()
    stream = stage.go(source, lazy=True)
    started_before_read = source_started.is_set()
    lazy_result = stream.get()
    sync_replay = list(stream)
    async_replay = asyncio.run(collect_async(stream))
    stage.close()

    async def failing_source():
        yield 3
        raise ValueError("source failed")

    failure_stage = Stage()
    failure_stream = failure_stage.go(failing_source)
    failure_values: list[int] = []
    try:
        failure_values.extend(failure_stream)
    except ValueError as error:
        failure_type = type(error).__name__
    try:
        failure_stream.get()
    except ValueError:
        pass
    failure_stage.close()

    print(f"started_before_read={started_before_read}")
    print(f"lazy_result={lazy_result}")
    print(f"sync_replay={sync_replay}")
    print(f"async_replay={async_replay}")
    print(f"failure_values={failure_values}")
    print(f"failure_type={failure_type}")


if __name__ == "__main__":
    main()
