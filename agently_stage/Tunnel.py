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

import asyncio
import queue
import threading
import time
import warnings

from .Stage import Stage


class Tunnel:
    """
    Agently Tunnel provide a convenient way to transport data cross threads and event loops and put them into a hybrid generator or a result list.

    Args:
    - `private_max_workers` (`int`): If you want to use a private thread pool executor, declare worker number here and the private thread pool executor will execute tasks instead of the global one in Agently Stage dispatch environment. Value `None` means use the global thread pool executor.Default value is `1`.
    - `max_concurrent_tasks` (`int`): If you want to limit the max concurrent task number that running in async event loop, declare max task number here. Value `None` means no limitation.
    - `on_error` (`function(Exception)->any`): Register a callback function to handle exceptions when running.
    - `timeout` (`int`): Seconds to wait next item when start pull out item from generator. Default value is `10`. Value `None` means never timeout.

    Example:
    ```
    from agently-stage import Stage, Tunnel
    with Stage() as stage:
        tunnel = Tunnel()
        async def wait_to_print():
            async for item in tunnel:
                print(item)
        stage.go(wait_to_print)
        tunnel.put("Hello")
        tunnel.put("Agently Tunnel")
        tunnel.put_stop()
    print(tunnel.get())
    ```
    """

    def __init__(
        self,
        wait_interval: float = 0.1,
        timeout: int = 10,
        timeout_after_start: bool = True,
    ):
        self._wait_interval = wait_interval
        self._timeout = timeout
        self._timeout_after_start = timeout_after_start
        self._started = False
        self._data_queue = queue.Queue()
        self._creage_generator_lock = threading.Lock()
        self._NODATA = object()
        self.generator = None

    def _create_generator(self):
        async def run_hybrid_generator():
            start_time = time.time()
            while True:
                data = self._NODATA
                if self._timeout_after_start and not self._started:
                    try:
                        data = self._data_queue.get_nowait()
                        self._started = True
                    except queue.Empty:
                        await asyncio.sleep(self._wait_interval)
                else:
                    try:
                        data = self._data_queue.get_nowait()
                    except queue.Empty:
                        if time.time() - start_time > self._timeout:
                            break
                        await asyncio.sleep(self._wait_interval)
                    if data is StopIteration:
                        break
                if data is not self._NODATA:
                    yield data

        with Stage() as stage:
            return stage.go(run_hybrid_generator())

    def _create_generator_stage(self):
        with self._creage_generator_lock:
            if self.generator is None:
                self.generator = self._create_generator()

    def get_generator(self):
        self._create_generator_stage()
        return self.generator

    def __iter__(self):
        self._create_generator_stage()
        yield from self.generator

    async def __aiter__(self):
        self._create_generator_stage()
        async for item in self.generator:
            yield item

    def __call__(self):
        self._create_generator_stage()
        return self.generator()

    def get(self):
        self._create_generator_stage()
        return self.generator.get()

    def put(self, data: any):
        """
        Put data into tunnel.

        Args:
        - `data` (any)
        """
        if not self._data_queue.empty() and self._data_queue.queue[-1] is StopIteration:
            warnings.warn("You can't put data into tunnel after put_stop()", RuntimeWarning, stacklevel=2)
            return
        self._data_queue.put(data)

    def put_stop(self):
        """
        Put stop sign into tunnel to tell all consumers data transportation is done.
        """
        self._data_queue.put(StopIteration)
