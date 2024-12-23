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

import atexit
import inspect
import threading
import asyncio
import functools
from typing import Callable, Union, List
from concurrent.futures import ThreadPoolExecutor
from .StageResponse import StageResponse
from .StageHybridGenerator import StageHybridGenerator
from .StageFunction import StageFunctionMixin, StageFunction

class BaseStage:
    _global_executor = None
    _global_max_workers = 5
    _executor_lock = threading.RLock()

    @staticmethod
    def _get_global_executor():
        if BaseStage._global_executor is None:
            with BaseStage._executor_lock:
                BaseStage._global_executor = ThreadPoolExecutor(max_workers=BaseStage._global_max_workers)
        return BaseStage._global_executor
        
    @staticmethod
    def set_global_max_workers(global_max_workers:int) -> None:
        """
        Set or reset max worker number of global thread pool executor.

        Args:
        - `global_max_workers` (`int`): Max worker number of global thread pool executor.

        Return: 
        - None
        """
        BaseStage._global_max_workers = global_max_workers
        with BaseStage._executor_lock:
            if BaseStage._global_executor:
                BaseStage._global_executor.shutdown(wait=True)
            BaseStage._global_executor = ThreadPoolExecutor(max_workers=BaseStage._global_max_workers)
            atexit.register(functools.partial(BaseStage._global_executor.shutdown, wait=True))

    def __init__(
            self,
            private_max_workers:int=None,
            max_concurrent_tasks:int=None,
            on_error:Callable[[Exception], any]=None,
            is_daemon:bool=False,
            closing_timeout:Union[float, int]=None,
        ):
        self._private_max_workers = private_max_workers
        self._max_concurrent_tasks = max_concurrent_tasks
        self._on_error = on_error
        self._is_daemon = is_daemon
        self._semaphore = None
        self._loop_thread = None
        self._loop = None
        self._private_executor = None
        self._loop_ready = threading.Event()
        self._responses = set()
        self._closing_timeout = closing_timeout
        self._closed = False
        self._errors = []
        if self._is_daemon:
            atexit.register(self.close)
    
    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.close()
        if type is not None and self._on_error is not None:
            self._on_error(value)
        return False

    @property
    def _executor(self):
        if self._private_max_workers:
            self._private_executor = (
                ThreadPoolExecutor(max_workers=self._private_max_workers)
                if self._private_executor is None
                else self._private_executor
            )
            return self._private_executor
        else:
            return BaseStage._get_global_executor()
    
    def _initialize(self):
        self._closed = False
        if (
            not self._loop_thread
            or not self._loop_thread.is_alive()
            or not self._loop
            or not self._loop.is_running()
        ):
            self._loop_thread = threading.Thread(target=self._start_loop, daemon=self._is_daemon)
            self._loop_thread.start()
            self._loop_ready.wait()

    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        self._loop.set_exception_handler(self._loop_exception_handler)
        if self._max_concurrent_tasks:
            self._semaphore = asyncio.Semaphore(self._max_concurrent_tasks)
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(lambda: self._loop_ready.set())
        self._loop.run_forever()
    
    def _loop_exception_handler(self, loop, context):
        if self._on_error is not None:
            loop.call_soon_threadsafe(self._on_error, context["exception"])
        else:
            raise context["exception"]
            #print(f"Stage dispatch environment captured exception when running: { context['exception'] }")
            #print(f"Use `.on_error()` to replace exception handler or use `.get_errors()` to check and handle all runtime exceptions.")
            #self._errors.append(context["exception"])
    
    def go(
            self,
            task:any,
            *args,
            on_success:Callable[[any], any]=None,
            on_error:Callable[[Exception], any]=None,
            lazy:bool=False,
            async_gen_interval:float=0.1,
            **kwargs
        )->Union[StageResponse, StageHybridGenerator]:
        """
        Start task in Agently Stage instance's dispatch environment.

        Example:
        ```
        def task(sentence, options:dict):
            print(sentence)
            for key, value in options.items():
                print(key, value)
            raise Exception("Some Error")
        
        stage.go(
            task,
            "hello world",
            options={"AgentlyStage": "is very cool!"},
            on_error=lambda e: print(e),
        )
        ```
        
        Args:
        - `task` (`function`, `method`, `functools.partial`, `generator`, `generatorfunction`, `coroutine`, `coroutinefunction`, `asyncio.Future`, `asyncgen`, `asyncgenfunction`): Task that need to be dispatched in Agently Stage environment.
        - `on_success` (`function(any)->any`): Register a callback function to handle task's successful return.
        - `on_error` (`function(Exception)->any`): Register a callback function to handle task's exception when running.
        - `lazy` (`bool`): To tell when should generator task or async generator task start running. Task will start running ONLY WHEN `StageHybridGenerator` is requested by `for` ,`next()`, `async for`, `anext()` if `lazy` is `True`. Task will start IMMEDIATELY and use a queue to store processing results and when `StageHybridGenerator` is requested those stored results can be used immediately. `lazy` has no use when response is `StageResponse`. Default value is `False`.
        - `async_gen_interval` (`float`): Time interval for waiting new item from `StageHybridGenerator`'s response queue when using `async for` or `anext()`. `async_gen_interval` is only useful when you want to use `StageHybridGenerator` as an async generator. Default value is `0.1`.
        - `*args`, `**kwargs`: Args and kwargs you want to pass to task when executing.

        Return:
        - `StageResponse`: When task is `function`, `method`, `functools.partial`, `coroutine`, `coroutinefunction`, `asyncio.Future`.
        - `StageHybridGenerator`: When task is `generator`, `generatorfunction`, `asyncgen`, `asyncgenfunction`.
        """
        if not self._loop or self._loop.is_running():
            self._initialize()
        response_kwargs = {
            "on_success": on_success,
            "on_error": on_error,
        }
        hybrid_generator_kwargs = {
            "on_success": on_success,
            "on_error": on_error,
            "lazy": lazy,
            "async_gen_interval": async_gen_interval,
        }
        if inspect.iscoroutine(task):
            if self._semaphore:
                if not self._semaphore.locked():
                    return StageResponse(self, task, **response_kwargs)
                else:
                    self._semaphore.acquire()
                    try:
                        return StageResponse(self, task, **response_kwargs)
                    finally:
                        self._semaphore.release()
            else:
                return StageResponse(self, task, **response_kwargs)
        elif inspect.isasyncgen(task):
            if self._semaphore:
                if not self._semaphore.locked():
                    return StageHybridGenerator(self, task, **hybrid_generator_kwargs)
                else:
                    self._semaphore.acquire()
                    try:
                        return StageHybridGenerator(self, task, **hybrid_generator_kwargs)
                    finally:
                        self._semaphore.release()
            else:
                return StageHybridGenerator(self, task, **hybrid_generator_kwargs)
        elif asyncio.isfuture(task):
            return StageResponse(self, task, **response_kwargs)
        elif inspect.isgenerator(task):
            async def async_generator():
                for item in task:
                    try:
                        result = await self._loop.run_in_executor(self._executor, lambda: item)
                        yield result
                    except Exception as e:
                        yield e
            return self.go(async_generator())
        elif inspect.iscoroutinefunction(task) or inspect.isasyncgenfunction(task):
            return self.go(task(*args, **kwargs), **hybrid_generator_kwargs)
        elif inspect.isgeneratorfunction(task):
            return self.go(task(*args, **kwargs), **hybrid_generator_kwargs)
        elif inspect.isfunction(task) or inspect.ismethod(task) or isinstance(task, functools.partial):
            return StageResponse(self, self._loop.run_in_executor(self._executor, lambda: task(*args, **kwargs)), **response_kwargs)
        elif isinstance(task, StageFunction):
            return task.go(*args, **kwargs)
        else:
            raise TypeError(f"Task seems like a value or an executed function not an executable task: { task }")
    
    def go_all(self, *task_list:List[any]):
        """
        Start multiple tasks in Agently Stage instance's dispatch environment.

        Example:
        ```
        stage.go_all(
            (task1, [arg1, arg2], { "kwarg1": ..., "on_error": lambda e: print(e) }),
            (task2, [], { "kwarg1": ... }),
            task3,
            task4,
            ...
        )
        ```

        Args:
        - `*task_list` (`[task or task setting tuple]`):
            - Tasks can be passed as individual arguments, each representing a callable task.
            - Tasks can also be defined as tuples in the following format:            
              `(<task_function>, [<arg_1>, <arg_2>, ...], {"<kwarg_key>": <kwarg_value>, ...})`
                - `<task_function>`: The task's callable function.
                - `[<arg_1>, <arg_2>, ...]`: A list of positional arguments for the task (optional).
                - `{"<kwarg_key>": <kwarg_value>, ...}`: A dictionary of keyword arguments for the task (optional).
        
        Return:
        - [<StageResponse or StageHybridGenerator of task_1>, ...]
        """
        response_list = []
        for task_setting in task_list:
            if isinstance(task_setting, (tuple, list)):
                if len(task_setting) >= 1:
                    task = task_setting[0]
                    args = task_setting[1] if len(task_setting) >= 2 else []
                    kwargs = task_setting[2] if len(task_setting) >= 3 else {}
                else:
                    raise ValueError("Stage .go_all() got an empty task setting from task list.")
                response = self.go(
                    task,
                    *args,
                    **kwargs,
                )
            else:
                response = self.go(task)
            response_list.append(response)
        return response_list

    def get(self, task:any, *args, **kwargs):
        """
        Start task in Agently Stage instance's dispatch environment and wait for the result.
        
        Example:
        ```
        def task(sentence, options:dict):
            result = ""
            result += f"{ sentence }\\n"
            for key, value in options.items():
                result += f"{ key } { value }\\n"
            return result
        
        stage.get(
            task,
            "hello world",
            options={"AgentlyStage": "is very cool!"},
        )
        ```
        
        Args:
        - `task` (`function`, `method`, `functools.partial`, `generator`, `generatorfunction`, `coroutine`, `coroutinefunction`, `asyncio.Future`, `asyncgen`, `asyncgenfunction`): Task that need to be dispatched in Agently Stage environment.
        - `on_success` (`function(any)->any`): Register a callback function to handle task's successful return.
        - `on_error` (`function(Exception)->any`): Register a callback function to handle task's exception when running.
        - `*args`, `**kwargs`: Args and kwargs you want to pass to task when executing.

        Return:
        - return of `task`: When task is `function`, `method`, `functools.partial`, `coroutine`, `coroutinefunction`, `asyncio.Future`.
        - a list of all items yielded by the generator of `task`: When task is `generator`, `generatorfunction`, `asyncgen`, `asyncgenfunction`.
        """
        response = self.go(task, *args, **kwargs)
        if isinstance(response, StageResponse):
            return response.get()
        elif isinstance(response, StageHybridGenerator):
            result = []
            for item in response:
                result.append(item)
            return result
    
    def get_all(self, *task_list:List[any]):
        """
        Start multiple tasks in Agently Stage instance's dispatch environment and wait for all the results.

        Example:
        ```
        stage.get_all(
            (task1, [arg1, arg2], { "kwarg1": ..., "on_error": lambda e: print(e) }),
            (task2, [], { "kwarg1": ... }),
            task3,
            task4,
            ...
        )
        ```

        Args:
        - `*task_list` (`[task or task setting tuple]`):
            - Tasks can be passed as individual arguments, each representing a callable task.
            - Tasks can also be defined as tuples in the following format:            
              `(<task_function>, [<arg_1>, <arg_2>, ...], {"<kwarg_key>": <kwarg_value>, ...})`
                - `<task_function>`: The task's callable function.
                - `[<arg_1>, <arg_2>, ...]`: A list of positional arguments for the task (optional).
                - `{"<kwarg_key>": <kwarg_value>, ...}`: A dictionary of keyword arguments for the task (optional).
        
        Return:
        - [<return result from StageResponse | result list from StageHybridGenerator>, ...]
        """
        responses = self.go_all(*task_list)
        result_list = []
        for response in responses:
            if isinstance(response, StageResponse) or isinstance(response, StageHybridGenerator):
                result_list.append(response.get())
            else:
                result_list.append(response)
        return result_list

    def on_error(self, handler:Callable[[Exception], any]):
        """
        Set exception handler for Agently Stage instance.

        Args:
        - `handler` (`function(Exception)->any`): Exception handler.
        """
        self._on_error = handler
    
    def get_errors(self):
        """
        Get all errors occurred during Agently Stage instance runtime.

        Return:
        - List[Exception]
        """
        return self._errors
    
    def close(self, timeout:Union[float, int]=None):
        """
        Close Agently Stage instance and its dispatch environment including async event loop, threads and private thread pool executor.

        Args:
        - `timeout` (`float` | `int`): Timeout seconds for waiting each still ongoing task when Agently Stage instance is closing. This parameter will have higher priority than `closing_timeout` which was set when Agently Stage instance was created.
        """
        if self._closed:
            return
        self._closed = True
        
        for response in self._responses.copy():
            if timeout is not None or self._closing_timeout is not None:
                response._result_ready.wait(
                    timeout=timeout if timeout is not None else self._closing_timeout
                )
            else:
                response._result_ready.wait()
            if isinstance(response, StageHybridGenerator):
                if not response._iter_consumed:
                    for _ in response:
                        pass
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop:
            pending = asyncio.all_tasks(self._loop)
            if pending:
                for task in pending:
                    task.cancel()
        if self._private_max_workers and self._private_executor is not None:
            self._private_executor.shutdown(wait=True)
            self._private_executor = None
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join()
            self._loop_thread = None
        if self._loop and not self._loop.is_closed():
            self._loop.close()
        self._loop = None

class Stage(BaseStage, StageFunctionMixin):
    """
    Agently Stage create an instance to manage multi-threads and async tasks in its dispatch environment.

    Stage dispatch environment will allow tasks managed by this Agently Stage instance to be run in an independent thread with an independent async event loop that will not disturb other tasks create or managed by other Agently Stage instance, other packages or other complex async/multi-threading logic.

    Args:
    - `private_max_workers` (`int`): If you want to use a private thread pool executor, declare worker number here and the private thread pool executor will execute tasks instead of the global one in this Agently Stage instance. Value `None` means use the global thread pool executor.
    - `max_concurrent_tasks` (`int`): If you want to limit the max concurrent task number that running in async event loop, declare max task number here. Value `None` means no limitation.
    - `on_error` (`function(Exception)->any`): Customize exception handler to handle exceptions those raised from tasks running in Agently Stage instance's dispatch environment.
    - `is_daemon` (`bool`): When Agently Stage instance is daemon, it will automatically close when main thread is closing.
    - `closing_timeout` (`float` | `int`): Timeout seconds for waiting each still ongoing task when Agently Stage instance is closing by `.close()` or is closing with main thread.

    Usage:
    
    ```
    from agently-stage import Stage

    async def task(sentence):
        print(sentence)
        return sentence

    # Basic Usage:
    stage = Stage()
    response = stage.go(task, "Agently Stage is so cool!")
    result = response.get()
    stage.close()

    # Use `with` to Manage Context
    with Stage() as stage:
        response = stage.go(task, "Using with is so convenient!")
    result = response.get()

    # Use decorator `@Stage.func` with default global Agently Stage instance
    @Stage.func
    def global_stage_func(sentence):
        print(sentence)
        return sentence
    global_stage_func("Run in global Agently Stage instance.")
    
    # Use decorator `@<stage instance>.func`
    with Stage() as stage:
        @stage.func
        def stage_func(sentence):
            print(sentence)
            return sentence
        stage_func("Run in Agently Stage instance.")
    ```
    """

    _global_stage = None

    @staticmethod
    def _get_global_stage():
        if Stage._global_stage is None:
            Stage._global_stage = Stage(is_daemon=True)
        return Stage._global_stage

    @staticmethod
    def func(func:any):
        """
        Decorator to transform a function to an Agently Stage Function using Agently Stage default global stage dispatch environment.

        Usage:
        ```
        import time
        from agently-stage import Stage

        @Stage.func
        def task(sentence):
            time.sleep(1)
            print("This sentence comes second because `time.sleep()` pause the process for 1 second.")
            return sentence
        
        task("Agently Stage is so cool!")
        print("This sentence comes first because `task()` will not block the way.")
        result = task.wait()
        print("This sentence comes third because `.wait()` hold the thread.")
        print(result)
        ```
        
        Args:
        - `func` (`function`, `method`, `functools.partial`, `generator`, `generatorfunction`, `coroutine`, `coroutinefunction`, `asyncio.Future`, `asyncgen`, `asyncgenfunction`): Function that need to be dispatched in Agently Stage environment.

        Return:
        - `StageFunction`
        """
        return StageFunction(Stage._get_global_stage(), func)