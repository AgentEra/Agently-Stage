from __future__ import annotations

import threading
import time

from agently_stage import Events


def test_event_wait_returns_payload_and_supports_timeout() -> None:
    events = Events()
    event = events.create("ready")

    assert event.wait(timeout=0.001) is None
    event.set({"value": 1})

    assert event.is_set()
    assert event.wait(timeout=0.001) == {"value": 1}
    event.clear()
    assert not event.is_set()
    assert event.get_data() is None


def test_wait_all_waits_for_event_objects_not_dictionary_keys() -> None:
    events = Events()
    first = events.create("first")
    second = events.create("second")

    def publish() -> None:
        time.sleep(0.01)
        first.set(1)
        second.set(2)

    publisher = threading.Thread(target=publish)
    publisher.start()
    events.wait_all()
    publisher.join()

    assert first.get_data() == 1
    assert second.get_data() == 2
