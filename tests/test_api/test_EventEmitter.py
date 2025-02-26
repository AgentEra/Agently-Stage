from __future__ import annotations

import asyncio
import random
import time

import pytest

from agently_stage import EventEmitter, Stage


def test_basic_emitter():
    emitter = EventEmitter()
    activated_count = 0

    def should_always_be_activated_handler(data):
        time.sleep(0.2)
        assert data == "It works"
        nonlocal activated_count
        activated_count += 1

    def should_be_activated_once_handler(data):
        time.sleep(0.2)
        assert data == "It works"
        nonlocal activated_count
        activated_count += 1

    def should_not_be_activated_handler(data):
        nonlocal activated_count
        activated_count += 1
        raise RuntimeError("Something wrong!")

    # Add long term listener
    emitter.on("test_1", should_always_be_activated_handler)
    assert "test_1" in emitter._listeners and emitter._listeners["test_1"][0] == should_always_be_activated_handler
    # Add long term listener but can not be triggered
    emitter.on("test_2", should_not_be_activated_handler)
    assert "test_2" in emitter._listeners and emitter._listeners["test_2"][0] == should_not_be_activated_handler
    # Add once listener
    emitter.once("test_1", should_be_activated_once_handler)
    assert "test_1" in emitter._once and emitter._once["test_1"][0] == should_be_activated_once_handler

    # First emit without wait
    emitter.emit("test_1", "It works", wait=False)
    assert activated_count == 0
    # Sleep to wait handlers done
    time.sleep(1)
    assert activated_count == 2
    # Second emit with wait, once listener should be removed
    emitter.emit("test_1", "It works", wait=True)
    assert activated_count == 3
    # Remove all listeners
    emitter.off("test_1", should_always_be_activated_handler)
    assert "test_1" in emitter._listeners and len(emitter._listeners["test_1"]) == 0
    # Third emit and no listener should be triggered
    emitter.emit("test_1", "It works", wait=True)
    assert activated_count == 3
    # Emit an event that has no listener
    emitter.emit("something")


def test_decorator():
    emitter = EventEmitter()
    counter = 0

    @emitter.on("test")
    def handler(data):
        nonlocal counter
        counter += 1
        assert data

    @emitter.once("test")
    def once_handler(data):
        nonlocal counter
        counter += 1
        assert data

    emitter.emit("test", True, wait=True)
    assert counter == 2


@pytest.mark.skip(reason="Something wrong when go out of with context that may cause on going tasks stuck.")
def test_stress():
    emitter = EventEmitter()
    test_times = 1000
    counter = {}
    for i in range(test_times):
        counter.update({str(i): False})

    @emitter.on("data")
    async def handler(data):
        nonlocal counter
        await asyncio.sleep(random.randint(1, 100) / 100)
        counter[str(data)] = True
        true_count = 0
        for _, value in counter.items():
            if value:
                true_count += 1
        # print("I got:", data, true_count, "/", len(counter.keys()))

    with Stage() as stage:
        for i in range(test_times):
            stage.go(emitter.emit, "data", i)
            # stage.go(handler, i)

    time.sleep(10)
    print("sub end")
    assert sum(counter.values()) == test_times
