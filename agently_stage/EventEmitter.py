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

from typing import Union, Callable, List
from .Stage import Stage

class EventEmitter:
    """
    Agently Stage EventEmitter provide an event-driven dispatch center to help developers to build event-driven application.

    Args:
    - `private_max_workers` (`int`): If you want to use a private thread pool executor, declare worker number here and the private thread pool executor will execute tasks instead of the global one in Agently Stage dispatch environment. Value `None` means use the global thread pool executor.
    - `max_concurrent_tasks` (`int`): If you want to limit the max concurrent task number that running in async event loop, declare max task number here. Value `None` means no limitation.
    - `on_error` (`function(Exception)->any`): Register a callback function to handle exceptions when running.

    Example:
    ```
    from agently-stage import EventEmitter
    emitter = EventEmitter()
    emitter.on("data", lambda data: print(data))
    emitter.emit("data", "Agently Stage EventEmitter is so easy to use!")
    ```
    """
    def __init__(
            self,
            exception_handler: Callable[[Exception], any]=None
        ):
        self._listeners = {}
        self._once = {}
        self._exception_handler = exception_handler
    
    def add_listener(self, event:str, listener:Callable[[any], any]):
        """
        Add a listener to event.

        Args:
        - `event` (str): Event string to be listened.
        - `listener` (function(*args, **kwargs)->any): Listener/handler to handle data from event that will be emitted.

        Return:
        - `listener`
        """
        if event not in self._listeners:
            self._listeners.update({ event: [] })
        if listener not in self._listeners[event]:
            self._listeners[event].append(listener)
        return listener
    
    def remove_listener(self, event:str, listener:Callable[[any], any]):
        """
        Remove a listener from event.

        Args:
        - `event` (str): Event string to be listened.
        - `listener` (function(*args, **kwargs)->any): The same listener pointer/address that was added.
        """
        if event in self._listeners and listener in self._listeners[event]:
            self._listeners[event].remove(listener)

    def remove_all_listeners(self, event_list:Union[str, List[str]]):
        """
        Remove all listeners from event.

        Args:
        - `event` (str | list): Event string or event string list that all listeners to be removed.
        """
        if isinstance(event_list, str):
            event_list = [event_list]
        for event in event_list:
            self._listeners.update({ event: [] })

    def on(self, event:str, listener:Callable[[any], any]):
        """
        Alias to `.add_listener()`. Add a listener to event.

        Args:
        - `event` (str): Event string to be listened.
        - `listener` (function(*args, **kwargs)->any): Listener/handler to handle data from event that will be emitted.

        Return:
        - `listener`
        """
        return self.add_listener(event, listener)
    
    def off(self, event:str, listener:Callable[[any], any]):
        """
        Alias to `.remove_listener()`. Remove a listener from event.

        Args:
        - `event` (str): Event string to be listened.
        - `listener` (function(*args, **kwargs)->any): The same listener pointer/address that was added.
        """
        return self.remove_listener(event, listener)

    def once(self, event:str, listener:Callable[[any], any]):
        """
        Add a listener that will only run once to event.

        Args:
        - `event` (str): Event string to be listened.
        - `listener` (function(*args, **kwargs)->any): Listener/handler that will only run once to handle data from event that will be emitted, after that this listener will be removed.

        Return:
        - `listener`
        """
        if event not in self._once:
            self._once.update({ event: [] })
        if listener not in self._listeners[event] and listener not in self._once[event]:
            self._once[event].append(listener)
        return listener
    
    def listener_count(self, event:str)->int:
        """
        Count registered listener number of event including normal listeners and once listeners.

        Args:
        - `event` (str): Event string to be listened.

        Return:
        - count of listeners
        """
        return len(self._listeners[event]) + len(self._once[event])
        
    def emit(self, event:str, *args, **kwargs):
        """
        Emit event with args and kwargs.

        Args:
        - `event` (str): Event string to be emit.
        - `*args`, `**kwargs`: Args and kwargs that can be accepted by listeners.

        Return:
        - `[<StageResponse | StageHybridGenerator>, ...]`: A list of responses of all ongoing Agently Stage tasks.
        """
        listeners_to_execute = []
        on_going_listeners = []
        if event in self._listeners:
            for listener in self._listeners[event]:
                listeners_to_execute.append((listener, args, kwargs))
        if event in self._once:
            for listener in self._once[event]:
                listeners_to_execute.append((listener, args, kwargs))
            self._once.update({ event: [] })
        with Stage(exception_handler=self._exception_handler) as stage:
            for listener, args, kwargs in listeners_to_execute:
                on_going_listeners.append(stage.go(listener, *args, **kwargs))
        return on_going_listeners