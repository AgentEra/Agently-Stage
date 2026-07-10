from __future__ import annotations

import asyncio

from agently_stage import Tunnel

# Expected key output from a real local run:
# sync_replay=[1, 2]
# async_replay=[1, 2]
# timeout_reader=[]
# later_reader=[3]
# failure_values=[4]
# failure_type=ValueError


async def collect_async(tunnel: Tunnel[int]) -> list[int]:
    return [item async for item in tunnel]


def main() -> None:
    replay: Tunnel[int] = Tunnel()
    replay.put(1)
    replay.put(2)
    replay.close()
    sync_replay = list(replay)
    async_replay = asyncio.run(collect_async(replay))

    timeout_channel: Tunnel[int] = Tunnel(timeout=0.01)
    timeout_reader = list(timeout_channel)
    timeout_channel.put(3)
    timeout_channel.close()
    later_reader = list(timeout_channel)

    failed: Tunnel[int] = Tunnel()
    failed.put(4)
    failed.fail(ValueError("source failed"))
    failure_values: list[int] = []
    try:
        failure_values.extend(failed)
    except ValueError as error:
        failure_type = type(error).__name__

    print(f"sync_replay={sync_replay}")
    print(f"async_replay={async_replay}")
    print(f"timeout_reader={timeout_reader}")
    print(f"later_reader={later_reader}")
    print(f"failure_values={failure_values}")
    print(f"failure_type={failure_type}")


if __name__ == "__main__":
    main()
