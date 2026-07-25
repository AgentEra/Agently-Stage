from __future__ import annotations

import asyncio

from agently_stage import Tunnel, TunnelLagError

# Expected key output from a real local run:
# sync_replay=[1, 2]
# async_replay=[1, 2]
# timeout_reader=[]
# later_reader=[3]
# failure_values=[4]
# failure_type=ValueError
# bounded_replay=[3, 4]
# lag_missed=2
# latest_subscription=[11]
# checkpoint_subscription=[10, 11]
# retained_range=(0, 2)


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

    bounded: Tunnel[int] = Tunnel(max_history=2)
    slow_reader = iter(bounded)
    bounded.put(0)
    assert next(slow_reader) == 0
    for item in range(1, 5):
        bounded.put(item)
    try:
        next(slow_reader)
    except TunnelLagError as error:
        lag_missed = error.missed_count
    bounded.close()
    bounded_replay = list(bounded)

    positioned: Tunnel[int] = Tunnel()
    positioned.put(10)
    latest_subscription = positioned.subscribe(start="latest", timeout=None)
    checkpoint_subscription = positioned.subscribe(start=0, timeout=None)
    positioned.put(11)
    positioned.close()

    print(f"sync_replay={sync_replay}")
    print(f"async_replay={async_replay}")
    print(f"timeout_reader={timeout_reader}")
    print(f"later_reader={later_reader}")
    print(f"failure_values={failure_values}")
    print(f"failure_type={failure_type}")
    print(f"bounded_replay={bounded_replay}")
    print(f"lag_missed={lag_missed}")
    print(f"latest_subscription={list(latest_subscription)}")
    print(f"checkpoint_subscription={list(checkpoint_subscription)}")
    print(f"retained_range={positioned.retained_range}")


if __name__ == "__main__":
    main()
