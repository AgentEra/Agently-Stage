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

import threading

class StageResponse:
    def __init__(
            self,
            stage,
            task,
            *,
            ignore_exception,
            on_success,
            on_error,
            on_finally,
        ):
        self._stage = stage
        self._task = task
        self._ignore_exception = ignore_exception
        self._on_success = on_success
        self._on_error = on_error
        self._on_finally = on_finally
        self._result = {
            "status": None,
            "result": None,
        }
        self._task.add_done_callback(self._on_task_done)
        self.result_ready = threading.Event()
    
    def _on_task_done(self, future):
        try:
            result = future.result()
            if isinstance(result, Exception):
                raise result
            self._result.update({
                "status": True,
                "result": (
                    result
                    if self._on_success is None
                    else self._on_success(result)
                ),
            }) 
        except Exception as e:
            self._result.update({
                "status": False,
                "result": (
                    e
                    if self._on_error is None
                    else self._on_error(e)
                ),
            })
            if self._on_error is None and not self._ignore_exception:
                self._stage._raise_exception(e)
        finally:
            if self._on_finally is not None:
                self._on_finally(self._result["result"])
            self.result_ready.set()
    
    def is_ready(self):
        return self.result_ready.is_set()
    
    def get(self):
        self.result_ready.wait()
        return self._result["result"]