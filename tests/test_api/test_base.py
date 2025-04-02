from __future__ import annotations


class Counter:
    def __init__(self):
        self.value = []

    def increment(self, value: str):
        self.value.append(value)

    @property
    def count(self):
        return len(self.value)
