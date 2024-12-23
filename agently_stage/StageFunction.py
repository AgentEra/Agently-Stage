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
from typing import Callable

class StageFunction:
    """
    Agently Stage Function transform a normal function to a function that can be start and wait in different timing.

    It seems like an async function but more powerful and can be used easier, just like the usages of async functions in node.js or Golang.

    Example:
    ```
    import time
    from agently-stage import Stage

    with Stage() as stage:
        @stage.func
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
    """
    def __init__(self, stage, func, *args, **kwargs):
        self._stage = stage
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._on_success_handler = None
        self._on_error_handler = None
        self._response = None
        self._on_going = threading.Event()
    
    def __call__(self, *args, **kwargs):
        return self.go(*args, **kwargs)
    
    def set(self, *args, **kwargs):
        """
        Set args and kwargs to Agently Stage Function

        Return:
        - `self`
        """
        self._args = args
        self._kwargs = kwargs
        return self
    
    def args(self, *args):
        """
        Set args to Agently Stage Function

        Return:
        - `self`
        """
        self._args = args
        return self
    
    def kwargs(self, **kwargs):
        """
        Set kwargs to Agently Stage Function

        Return:
        - `self`
        """
        if not isinstance(self._kwargs, dict):
            self._kwargs = {}
        for key, value in kwargs.items():
            self._kwargs.update({key, value})
        return self
    
    def on_success(self, on_success_handler:Callable[[any], any]):
        """
        Set success callback handler to Agently Stage Function

        Args:
        - `on_success_handler` (`function(any)->any`)

        Return:
        - `self`
        """
        self._on_success_handler = on_success_handler
        return self

    def on_error(self, on_error_handler):
        """
        Set exception handler to Agently Stage Function

        Args:
        - `on_error_handler` (`function(Exception)->any`)

        Return:
        - `self`
        """
        self._on_error_handler = on_error_handler
        return self

    def go(self, *args, **kwargs):
        """
        Start Agently Stage Function in Stage instance. Will return same ongoing response instance if Agently Stage Function has already started.

        Alias:
        ```
        # These 2 expressions are the same
        stage_func.go(*args, **kwargs)
        stage_func(*args, **kwargs)
        ```

        Args:
        - `*args`
        - `**kwargs`

        Return:
        - `StageResponse`: When Agently Stage Function is `function`, `method`, `functools.partial`, `coroutine`, `coroutinefunction`, `asyncio.Future`.
        - `StageHybridGenerator`: When Agently Stage Function is `generator`, `generatorfunction`, `asyncgen`, `asyncgenfunction`.
        """
        if self._response:
            return self._response
        if len(args) > 0:
            self.args(*args)
        if len(kwargs.keys()) > 0:
            self.kwargs(**kwargs)
        self._response = self._stage.go(
            self._func,
            *self._args,
            on_success=self._on_success_handler,
            on_error=self._on_error_handler,
            **self._kwargs
        )
        self._on_going.set()
        return self._response
    
    def get(self, *args, **kwargs):
        """
        Start Agently Stage Function in Stage instance and wait for its result. Will return result from same stage response instance if Agently Stage Function has already started.

        Args:
        - `*args`
        - `**kwargs`

        Return:
        - return of Agently Stage Function: When Agently Stage Function is `function`, `method`, `functools.partial`, `coroutine`, `coroutinefunction`, `asyncio.Future`.
        - a list of all items yielded by the generator of Agently Stage Function: When Agently Stage Function is `generator`, `generatorfunction`, `asyncgen`, `asyncgenfunction`.
        """
        if self._response:
            return self._response.get()
        else:
            self.go(*args, **kwargs).get()
    
    def wait(self):
        """
        Wait Agently Stage Function to finish without start it while you try to start this function somewhere else.

        Return:
        - return of Agently Stage Function: When Agently Stage Function is `function`, `method`, `functools.partial`, `coroutine`, `coroutinefunction`, `asyncio.Future`.
        - a list of all items yielded by the generator of Agently Stage Function: When Agently Stage Function is `generator`, `generatorfunction`, `asyncgen`, `asyncgenfunction`.
        """
        self._on_going.wait()
        return self._response.get()
    
    def reset(self):
        """
        Reset Agently Stage Function to make it can be start again.
        
        Reset will clear ongoing stage response instance and ongoing signal so:
        
        - `.go()` and `.get()` will re-run the Agently Stage Function again and create a new ongoing response instance, instead of return from already ongoing stage response.
        - `.wait()` will be waiting another `.go()` after `.reset()`.

        """
        self._on_going.clear()
        self._response = None
        return self

class StageFunctionMixin:
    def func(self, func:any)->StageFunction:
        """
        Decorator to transform a function to an Agently Stage Function

        Usage:
        ```
        import time
        from agently-stage import Stage

        with Stage() as stage:
            @stage.func
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
        return StageFunction(self, func)