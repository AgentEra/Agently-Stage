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

import asyncio
import threading

class StageResponse:
    """
    Response of an Agently Stage Task

    Methods:

    - `get()`: get result
    - `get_final()`: get result from success callback
    """
    def __init__(self, stage, task, on_success=None, on_error=None):
        self._stage = stage
        self._stage._responses.add(self)
        self._loop = self._stage._loop
        self._result_ready = threading.Event()
        self._status = None
        self._result = None
        self._error = None
        self._final_response = None
        self._on_success = on_success
        self._on_error = on_error
        if asyncio.iscoroutine(task):
            self._task = asyncio.run_coroutine_threadsafe(task, self._loop)
        elif asyncio.isfuture(task):
            self._task = task
        self._task.add_done_callback(self._on_task_done)
    
    def _on_task_done(self, future):
        try:
            self._status = True
            self._result = future.result()
            if self._on_success:
                self._final_response = self._stage.go(self._on_success, self._result)
        except Exception as e:
            self._status = False
            self._error = e
            if self._on_error:
                self._final_response = self._stage.go(self._on_error, self._error)
            else:    
                raise self._error
        finally:
            self._result_ready.set()
            self._stage._responses.discard(self)
    
    def get(self):
        """
        Block process and wait for the result from ongoing Agently Stage task.
        """
        self._result_ready.wait()
        if self._final_response is not None:
            self._final_response.get()
        if self._status == True:
            return self._result
        elif self._on_error is None:
            raise self._error
    
    def get_final(self):
        """
        Block process and wait for the result after success callback handler executed from ongoing Agently Stage task.
        """
        self._result_ready.wait()
        if self._final_response is not None:
            return self._final_response.get()
        else:
            return self._result