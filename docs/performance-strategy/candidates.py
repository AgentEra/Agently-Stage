"""Experiment-only mechanisms; never imported by the production package."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from agently_stage import Tunnel


class ChunkStore:
    """Append, absolute-index lookup and eviction; retains partial head block."""

    def __init__(self, size=256):
        self.size = size
        self.blocks = {}
        self.start = 0
        self.end = 0

    def __len__(self):
        return self.end - self.start

    def append(self, value):
        block, offset = divmod(self.end, self.size)
        if offset == 0:
            self.blocks[block] = []
        self.blocks[block].append(value)
        self.end += 1

    def __getitem__(self, index):
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        block, offset = divmod(self.start + index, self.size)
        return self.blocks[block][offset]

    def popleft(self):
        value = self[0]
        block, offset = divmod(self.start, self.size)
        self.blocks[block][offset] = None
        self.start += 1
        if self.start % self.size == 0:
            del self.blocks[block]
        return value

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]


class ReplayTunnel(Tunnel):
    def __init__(self, storage="deque", **kwargs):
        super().__init__(**kwargs)
        if storage == "list":
            if kwargs.get("max_history") is not None:
                raise ValueError("list candidate supports unbounded history only")
            self._items = []
        elif storage == "chunk":
            self._items = ChunkStore()


class WakeTunnel(Tunnel):
    def __init__(self, wake="baseline", **kwargs):
        super().__init__(**kwargs)
        self.wake = wake
        self.notifications = 0
        self.resolutions = 0

    @staticmethod
    def resolve_many(waiters):
        for waiter in waiters:
            if not waiter.future.done():
                waiter.future.set_result(None)

    def _wake_waiters_locked(self):
        if self.wake == "baseline":
            self.notifications += len(self._async_waiters)
            self.resolutions += len(self._async_waiters)
            return super()._wake_waiters_locked()
        self._condition.notify_all()
        groups = defaultdict(list)
        for waiter in self._async_waiters:
            groups[waiter.loop].append(waiter)
        self._async_waiters.clear()
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        for loop, waiters in groups.items():
            self.notifications += 1
            self.resolutions += len(waiters)
            try:
                if self.wake == "local" and current is loop:
                    loop.call_soon(self.resolve_many, waiters)
                else:
                    loop.call_soon_threadsafe(self.resolve_many, waiters)
            except RuntimeError:
                for waiter in waiters:
                    waiter.future.cancel()
