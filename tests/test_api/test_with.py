import asyncio
import time
from agently_stage import Stage

class Counter:
    def __init__(self):
        self.value = []

    def increment(self, value: str):
        self.value.append(value)

def test_with():
    counter = Counter()

    with Stage() as stage:
        async def async_task(value: str):
            counter.increment(f"async_task start {value}")
            await asyncio.sleep(1)
            counter.increment(f"async_task end {value}")

        def sync_task(value: str):
            counter.increment(f"sync_task start {value}")
            time.sleep(2)
            counter.increment(f"sync_task end {value}")

        async_response = stage.go(async_task, "1")
        sync_response = stage.go(sync_task, "2")
        assert stage.closed is False

    assert stage.closed is True
    async_response.get()
    sync_response.get()
    expected_values = [
        "async_task start 1",
        "sync_task start 2",
        "async_task end 1",
        "sync_task end 2",
    ]
    assert all(value in counter.value for value in expected_values)


if __name__ == "__main__":
    test_with()
