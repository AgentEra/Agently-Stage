# Copyright 2024 Maplemx(Mo Xin), AgentEra Ltd. Agently Team(https://Agently.tech)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Contact us: Developer@Agently.tech
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concurrent.futures import Future

    from agently_stage import Stage


@dataclass
class TaskResult:
    result: any | None = field(default=None)
    status: bool | None = field(default=None)


class StageResponse:
    def __init__(
        self,
        stage: Stage,
        task: Future,
    ):
        self._stage = stage
        self._stage._responses.add(self)
        self._task = task
        self.result_ready = threading.Event()
        self._result = TaskResult()
        self._task.add_done_callback(self._on_task_done)

    def _on_task_done(self, future):
        try:
            result = future.result()
            if isinstance(result, Exception):
                raise result
            self._result = TaskResult(status=True, result=result)
        except Exception as e:
            self._result = TaskResult(status=False, result=e)
        finally:
            self.result_ready.set()
            self._stage._responses.discard(self)

    def is_ready(self):
        return self.result_ready.is_set()

    def get(self):
        self.result_ready.wait()
        return self._result.result
