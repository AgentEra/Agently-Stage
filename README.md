<p style = "text-align:center"><img style="width:80%" src=https://github.com/user-attachments/assets/c49ef73e-9ea6-42c8-88a4-ecd38e576b7a></img></p>

# Agently Stage

> *Efficient Convenient Asynchronous & Multithreaded Programming*

[![license](https://img.shields.io/badge/license-Apache2.0-blue.svg?style=flat-square)](https://github.com/AgentEra/Agently-Stage/blob/main/LICENSE)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/agently-stage?style=flat-square)](https://pypistats.org/packages/agently-stage)
[![GitHub star chart](https://img.shields.io/github/stars/agentera/agently-stage?style=flat-square)](https://star-history.com/#agentera/agently-stage)
[![Twitter](https://img.shields.io/twitter/url/https/twitter.com/AgentlyTech.svg?style=social&label=Follow%20%40AgentlyTech)](https://x.com/AgentlyTech)

## Install

```shell
pip install agently-stage
```

## What is Agently Stage?

Asynchronous and multithreaded programming in Python has always been complex and confusing, especially when building applications for GenAI. In <a src="https://github.com/AgentEra/Agently">Agently AI application development framework</a>, we’ve introduced numerous solutions to enhance control over GenAI outputs. For example, with Agently Instant Mode, you can perform streaming parsing of formatted data like JSON while generating structured results. Additionally, Agently Workflow allows you to orchestrate scheduling relationships between multiple GenAI request results.

As we delved deeper into controlling GenAI outputs, we recognized that the inherent complexity of combining asynchronous and multithreaded programming in Python poses a significant challenge. This complexity often hinders developers from leveraging GenAI capabilities efficiently and creatively.

To address this issue, we’ve spun off Agently Stage, a dedicated management solution specifically designed for mixed asynchronous and multithreaded programming, from the core Agently AI application development framework. With Agently Stage, we aim to empower developers to seamlessly manage mixed programming paradigms in Python.

Read on to discover how Agently Stage can revolutionize your approach to asynchronous and multithreaded programming, delivering a new era of efficiency and simplicity!

## Quick Overview of Core Features

### Use `Stage` to Manage Asynchronous and Multithreaded Programming

With Agently Stage, you can just use `stage.go()` to start asynchronous function or normal function in main thread or any other thread. `stage.go()` will return a `StageResponse`/`StageHybridGenerator` instance for you. You can use `response.get()` to wait for the result some time after, or not if you don't care.

```python
import time
import asyncio
from agently_stage import Stage

async def async_task(input_sentence:str):
    print("Start Simulate Async Network Request...")
    await asyncio.sleep(1)
    print("Response Return...")
    return f"Network Request Data: Your input is { input_sentence }"

def sync_task(a:int, b:int):
    print("Start Simulate Sync Long Time Task...")
    time.sleep(2)
    print("Task Done...")
    return f"Task Result: { a + b }"

stage = Stage()
async_response = stage.go(async_task, "Agently Stage is awesome!")
sync_response = stage.go(sync_task, 1, 2)
stage.close()
#Try remove this line below, it'll work perfectly too.
print(async_response.get(), "|", sync_response.get())
```

```text
Start Simulate Sync Long Time Task...
Start Simulate Async Network Request...
Response Return...
Task Done...
Network Request Data: Your input is Agently Stage is awesome! | Task Result: 3
```

You can use `with` to make code expression and context management easier:

```python
with Stage() as stage:
    async_response = stage.go(async_task, "Agently Stage is awesome!")
    sync_response = stage.go(sync_task, 1, 2)

print(async_response.get(), "|", sync_response.get())
```

By default, each Stage dispatch environment has 1 independent thread for its coroutine tasks and share a public thread executor pool with 5 executor workers with other Stage dispatch environments for its sync task. But you can adjust that as your wish with parameters when creating Stage instance:

- `private_max_workers` (`int`): If you want to use a private thread pool executor, declare worker number here and the private thread pool executor will execute tasks instead of the global one in this Agently Stage instance. Value `None` means use the global thread pool executor.
- `max_concurrent_tasks` (`int`): If you want to limit the max concurrent task number that running in async event loop, declare max task number here. Value `None` means no limitation.
- `on_error` (`function(Exception)->any`): Customize exception handler to handle exceptions those raised from tasks running in Agently Stage instance's dispatch environment.
- `is_daemon` (`bool`): When Agently Stage instance is daemon, it will automatically close when main thread is closing.
- `closing_timeout` (`float` | `int`): Timeout seconds for waiting each still ongoing task when Agently Stage instance is closing by `.close()` or is closing with main thread.

If you want to adjust the worker's number in public thread pool executor, you can use static method `Stage.set_global_max_workers(<new_worker_number>)` to do so.

### `StageFunction`: Transform a Normal Function into a Non-Blocking Function with Status

Decorator `@<stage_instance>.func` can transform a normal function into `StageFunction` instance with status management which can be started without blocking current thread in one place and wait for result in other places. `StageFunction` will be run in the dispatch environment provided by `Stage` instance.

```python
import time
from agently_stage import Stage
stage = Stage()

@stage.func
def task(sentence:str):
    time.sleep(1)
    return f"Done: { sentence }"

# Defined but hasn't run
task

# Start running
task.go("First")
# or just `task()` like call a function normally

# Block current thread and wait until done to get result
result = task.wait()
print(result)

# Wait again won't restart it
result_2 = task.wait()
print(result_2)

# Reset make the function can be started again
task.reset()
task("Second")
result_3 = task.wait()
print(result_3)
```

```text
Done: First
Done: First
Done: Second
```

How can this be useful? Think about a scenario like this:

```python
import time
import asyncio
from agently_stage import Stage

# We create a handler in one dispatch
# Param `is_daemon=True` can set Stage dispatch thread as a daemon thread
# so that Stage dispatch thread can close automatically with main thread
stage_1 = Stage(is_daemon=True)
@stage_1.func
async def handler(sentence):
    return f"Someone said: { sentence }"
    
# We wait this handler in another dispatch
stage_2 = Stage(is_daemon=True)
def waiting():
    result = handler.wait()
    print(result)
stage_2.go(waiting)

# We start this handler in the third dispatch some uncertain time after
time.sleep(1)
stage_3 = Stage(is_daemon=True)
async def executor():
    await asyncio.sleep(1)
    handler("StageFunction is useful!")
stage_3.go(executor)
```

```text
Someone said: StageFunction is useful!
```

### `StageHybridGenerator`: Iter Generator and Async Iter Generator Can Work in `Stage` too!

If you try to run a generator function with Agently Stage, you will get a `StageHybridGenerator` instance as response. You can iterate over `StageHybridGenerator` using `for`/`async for` or call `next()`/`anext()` explicitly. You can also use this feature to transform an iter generator into an async iter generator or otherwise. In fact, using `StageHybridGenerator` you don't event need to care about if this generator is an iter generator or an async iter generator anymore!

```python
import asyncio
from agently_stage import Stage
with Stage() as stage:
    async def start_gen(n:int):
        for i in range(n):
            await asyncio.sleep(1)
            yield i+1
    gen = stage.go(start_gen, 5)
    for item in gen:
        print(item)
```

```text
1
2
3
4
5
```

You can also use `<StageHybridGenerator instance>.get()` to get all results yielded from the generator function processing as items in a result list.

```python
import asyncio
from agently_stage import Stage
with Stage() as stage:
    async def start_gen(n:int):
        for i in range(n):
            await asyncio.sleep(1)
            yield i+1
    gen = stage.go(start_gen, 5)
    result_list = gen.get()
    print(result_list)
```

```text
[1, 2, 3, 4, 5]
```

By default, generator function will be processed immediately when `stage.go(<generator>)` no matter how later `StageHybridGenerator` be used. But if you want to preserve the characteristic of an iter generator that starts execution only when called, you can use parameter `lazy=True` in `stage.go()` to do so.

```python
gen = stage.go(start_gen, 5, lazy=True)
time.sleep(5)
# Generator function `start_gen` start here only when gen is iterated over by `for`
for item in gen:
    print(item)
```

And when iterating over an async iter generator, we need to use await in the consumer to hand over coroutine control. If the interval between await calls is too short, it can increase CPU load, while a longer interval might affect execution efficiency. We have set this interval to `0.1 seconds` by default, but you can adjust it using parameter `async_gen_interval` in `stage.go()`.

```python
gen = stage.go(start_gen, 5, async_gen_interval=0.5)
```

### `Tunnel`: Streaming Data Transportation Between Threads and Coroutines is SO EASY!

Transporting data between threads and coroutines in a streaming manner is so usual in GenAI developments because that's exactly how gen models work - predicting token by token. The work pattern from the source will directly influence the execution style of all subsequent downstream tasks. So we created `Tunnel` to make tasks like this easier.

```python
import time
import asyncio
from agently_stage import Stage, Tunnel

tunnel = Tunnel()

async def provider(n:int):
    for i in range(n):
        tunnel.put(i + 1)
        await asyncio.sleep(0.1)
    tunnel.put_stop()

def consumer():
    time.sleep(1)
    # You can use `tunnel.get_gen()` to get a `StageHybridGenerator` from tunnel instance
    gen = tunnel.get_gen()
    for data in gen:
        print("streaming:", data)

async def async_consumer():
    # Or you can just iterate over tunnel data by `for`/`async for`
    async for data in tunnel:
        print("async streaming:", data)

stage_1 = Stage()
stage_2 = Stage()
stage_3 = Stage()
stage_1.go(consumer)
stage_2.go(async_consumer)
stage_3.go(provider, 5)
stage_1.close()
stage_2.close()
stage_3.close()
# You can also use `tunnel.get()` to get a final yielded item list
print(tunnel.get())
```

```text
async streaming: 1
async streaming: 2
async streaming: 3
async streaming: 4
async streaming: 5
streaming: 1
streaming: 2
streaming: 3
streaming: 4
streaming: 5
```

Sometimes, we won't know if the data transporation from upstream is done or not and want to set a timeout to stop waiting, parameter `timeout` when creating Tunnel instance or in `.get_gen()`, `.get()` will help us to do so. By default, we set this timeout to `10 seconds`. You can set timeout value as `None` manually if you want to keep waiting no matter what.

```python
from agently_stage import Tunnel
tunnel = Tunnel(timeout=None)
# Timeout setting in .get_gen() or .get() will have higher priority
gen = tunnel.get_gen(timeout=1)
# But timeout setting only works at the first time that start the generator consumer
# In this case, that's `tunnel.get_gen()`, not `tunnel.get()`
result_list = tunnel.get(timeout=5)
```

### `EventEmitter`: Use It EXACTLY THE SAME AS IT SHOULD BE USED IN NODEJS

In Python, especially when you're a senior node.js coder, if you want to build a copy module of EventEmitter from node.js, you will feel something is not right. How so? It's because if you want to allow event listener to be an async function, you have to make the event executor function that will call event listener also an async function. In simple way to build a copy module of EventEmitter, that means `.emit()` must be an async function. And here's the funny part: we have to put an `await` before we call `emitter.emit()`. That's ridiculous because we can not ensure that we emit event in an async environment!

But event-driven development is so important to asynchronous and multithreaded programming, a REAL EventEmitter that WORKS EXACTLY THE SAME AS IT SHOULD BE USED IN NODEJS is required with no doubts.

So Agently Stage privode you an `EventEmitter` can be used like this:

```python
from agently_stage import Stage, EventEmitter

emitter = EventEmitter()

async def listener(data):
    print(f"I got: { data }")

emitter.on("data", listener)

with Stage() as stage:
    stage.go(lambda: emitter.emit("data", "EventEmitter is Cool!"))

emitter.emit("data", "I'll say it again, EventEmitter is Cool!")
```

```text
I got: EventEmitter is Cool!
I got: I'll say it again, EventEmitter is Cool!
```

No `asyncio.run()`! No `await emitter.emit()`! No worries about fxxking event loops! JUST `.emit()` WHEREVER YOU WANT!💪💪💪

---

## Something More

`Agently Stage` is part of our main work <a src="https://github.com/AgentEra/Agently">Agently AI application development framework</a> which aim to make GenAI application development faster, easier and smarter. Please ⭐️ this project and maybe try Agently framework by `pip install Agently` later, thank you!

If you want to contact us, email to <a href="mailto:developer@agently.tech">developer@agently.tech</a>, leave comments in <a href="https://github.com/AgentEra/Agently-Stage/issues">Issues</a> or <a href="https://github.com/AgentEra/Agently-Stage/discussions">Discussions</a> or leave messages to our X:[![Twitter](https://img.shields.io/twitter/url/https/twitter.com/AgentlyTech.svg?style=social&label=Follow%20%40AgentlyTech)](https://x.com/AgentlyTech)