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

import queue
import threading
from typing import Callable
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
            private_max_workers:int=1,
            max_concurrent_tasks:int=None,
            on_error:Callable[[Exception], any]=None,
            timeout:int=10
        ):
        self._private_max_worker = private_max_workers
        self._max_concurrent_tasks = max_concurrent_tasks
        self._on_error = on_error
        self._timeout = timeout
        self._data_queue = queue.Queue()
        self._close_event = threading.Event()
        self._stage = None
        self._ongoing_gen = None
        self._results = []
        self._NODATA = object()
        self._lock = threading.RLock()
    
    def _defer_close_stage(self):
        def close_stage():
            self._close_event.wait()
            self._stage.close()
            self._stage = None
        defer_thread = threading.Thread(target=close_stage)
        defer_thread.start()
    
    def _get_stage(self):
        if self._stage is not None:
            return self._stage
        else:
            self._stage = Stage(private_max_workers=self._private_max_worker, max_concurrent_tasks=self._max_concurrent_tasks, on_error=self._on_error)
            return self._stage
    
    def put(self, data:any):
        """
        Put data into tunnel.

        Args:
        - `data` (any)
        """
        self._data_queue.put(data)
    
    def put_stop(self):
        """
        Put stop sign into tunnel to tell all consumers data transportation is done.
        """
        self._data_queue.put(StopIteration)
    
    def get_gen(self, timeout:int=None):
        """
        Get Agently Stage Hybrid Generator to consumer data in tunnel.

        Args:
        - `timeout` (int): Seconds to wait next item when start pull out item from generator. This parameter will have higher priority than the one was set when Tunnel instance was created.

        Return:
        - `StageHybridGenerator`
        """
        with self._lock:
            if self._ongoing_gen is None:
                self._defer_close_stage()
                stage = self._get_stage()
                def queue_consumer():
                    while True:
                        data = self._NODATA
                        try:
                            if timeout is not None or self._timeout is not None:
                                data = self._data_queue.get(
                                    timeout=timeout if timeout is not None else self._timeout
                                )
                            else:
                                data = self._data_queue.get()
                        except queue.Empty:
                            continue
                        if data is StopIteration:
                            break
                        if data is not self._NODATA:
                            self._results.append(data)
                            yield data
                    self._close_event.set()
                self._ongoing_gen = stage.go(queue_consumer)
            return self._ongoing_gen
    
    def __iter__(self):
        gen = self.get_gen()
        for item in gen:
            yield item
    
    async def __aiter__(self):
        gen = self.get_gen()
        async for item in gen:
            yield item

    def get(self, timeout:int=None):
        """
        Get all items from tunnel into an item list.

        Args:
        - `timeout` (int): Seconds to wait next item when start pull out item from generator. This parameter will have higher priority than the one was set when Tunnel instance was created.

        Return:
        - `List[<item>]`
        """
        gen = self.get_gen(timeout=timeout)
        return gen.get()