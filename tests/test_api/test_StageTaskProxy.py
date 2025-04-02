from __future__ import annotations

import unittest

from agently_stage import StageTask, StageTaskProxy

from .test_base import Counter


class TestStageTaskProxy(unittest.TestCase):
    def test_stage_task_proxy(self):
        counter = Counter()
        stp = StageTaskProxy(lambda: counter.increment("test_stage_task_proxy"))

        self.assertIsNotNone(stp._func)
        self.assertIsNone(stp._on_success)
        self.assertIsNone(stp._on_error)
        self.assertIsNone(stp._on_finally)

        stp.add_on_success(StageTask(lambda res: counter.increment("on_success 1")))
        stp.add_on_error(StageTask(lambda: counter.increment("on_error 1")))
        stp.add_on_finally(StageTask(lambda: counter.increment("on_finally 1")))

        self.assertIsNotNone(stp._on_success)
        self.assertIsNotNone(stp._on_error)
        self.assertIsNotNone(stp._on_finally)

        stp()

        self.assertIn("test_stage_task_proxy", counter.value)
        self.assertIn("on_success 1", counter.value)
        self.assertIn("on_finally 1", counter.value)
        self.assertNotIn("on_error 1", counter.value)
        self.assertEqual(counter.count, 3)
