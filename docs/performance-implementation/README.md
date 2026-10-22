# 性能策略落地：默认行为、可选配置与代价

本目录对应 `feature/performance-strategy-evaluation` 的实现候选，尚未发布。
历史研究与原始数据完整保留在 [performance-strategy](../performance-strategy/README.md)，
本轮验证独立保存于 `evidence/`，不改写原研究结论或校验清单。
研究脚本提交前仅做格式规范；原字节快照与恢复方法见
[脚本维护记录](../performance-strategy/SCRIPT_REVISIONS.md)。

## 选择原则与逐项决定

默认项要求公共语义兼容、收益来源明确；依赖业务目标或负载的选择交给调用者。
“优先保留”表示值得实施和验证，不自动意味着默认开启。CPU 占满不是唯一目标，
同时关注吞吐、尾延迟、内存、线程预算、取消和完整交付。

| 命题 | 默认行为 | 显式选择与推荐场景 | 代价和未采用项 |
|---|---|---|---|
| H1 提交粒度 | 每次 `go` 保持独立句柄、上下文和取消边界 | 大量微小协程本来共享一次结果/生命周期时，用一个 async 根任务和 `stage.create_task` 展开；自行限制扇出 | 不自动批处理；业务独立任务仍逐个提交；根并发上限不限制子任务数量 |
| H2 carrier 数量 | `runtime.carrier_loop_count=1` | 多个独立 scope 确有 lane 竞争时，启动前实测增加 | 增加线程；单活跃 scope 仍绑定一个 loop；不按 CPU 数自动扩张 |
| H3 计算边界 | 阻塞函数使用共享线程池 | 阻塞 I/O 或释放 GIL 的原生计算用线程；纯 Python 粗粒度 CPU 工作显式使用应用进程池 | 小任务 IPC/序列化更慢；Stage 的 context-bound 提交不能直接交给进程/子解释器池 |
| H4 回放存储 | 无界 Tunnel 使用 list 常数索引；有界 Tunnel 保留 deque 快速淘汰；StageStream 自动受益 | `max_history=N` 仅在允许历史过期时设置 | 无界仍 O(N) 内存，get 额外复制；有界慢读者报 lag；不提供 storage 开关，不上线小历史退步的 Python 分块候选 |
| H5 通知 | `wake_mode="individual"` | 同一 loop 有很多等待订阅者，通知开销占比高时试 `"grouped"` | 合并 callback 不合并数据，不引入等待窗口；小扇出可能更慢，P99 可能恶化；不实现 local/自动切换 |
| H6 线程预算 | 共享池，不自动按任务耗时分类 | 短请求 SLA 优先且被慢任务挤占时，用不同 Stage 的 `max_workers`，或不同 `executor` 隔离 | 固定总预算分配会增加长任务总完成时间；多个私有池可能超配线程 |
| H7 正确性 | body 与 settlement、contextvars、取消、独立读者、lag、终态合同不变 | 测试为硬门槛 | 不通过移动 callback 线程或提前宣称完成来换取性能 |
| H8 Go/Rust | 保留 Python 调度 | 粗粒度热点通过普通 Python 函数包装释放 GIL 的原生计算，并在计算侧批量处理 | FFI/内存转换、构建维护成本；不能推出整体重写必要性；裸 ctypes callable 分类递归仍为已知限制 |
| H9 loop/解释器 | 标准 asyncio，无可选依赖自动安装 | uvloop 由应用创建 caller loop 后使用 Stage；对照真实 I/O 负载 | 微任务收益不代表整个应用收益；free-threaded 未验证，透明子解释器后端不支持 |

H4 的算法依据与 Python 官方 [deque 文档](https://docs.python.org/3.10/library/collections.html#collections.deque)
一致：中间索引退化为 O(N)。通知在 owner loop 完成 Future，遵守
[asyncio 跨线程约束](https://docs.python.org/3.10/library/asyncio-dev.html#concurrency-and-multithreading)。
研究的量化结论见 [原报告](../performance-strategy/REPORT.md)；本候选的实测见 [验证报告](VALIDATION.md)。

## 推荐用法

### 普通异步服务与微任务分组

```python
import asyncio
from agently_stage import Stage

async def item(value):
    await asyncio.sleep(0)
    return value * 2

async def main():
    async with Stage() as stage:
        # 原生 async 服务复用 caller loop，无需跨线程桥接。
        result = await stage.go(item, 21).async_get()
    return result
```

大量关联任务可以在一个根协程内 `stage.create_task(item(...), origin="batch item")` 后 gather。
选择这种写法意味着它们共享一次结果、异常与取消策略。`asyncio.gather` 默认
遇到首个异常就抛出，不自动取消兄弟；若业务要求失败即取消，应在 `finally` 中
显式取消并 await 所有子任务。Stage settlement 仍要等待其拥有的工作清理完成。
可运行示例 [performance_options.py](../../examples/performance_options.py) 展示这一边界。
不能把无限输入一次全部创建成 task；按应用容量分批或使用 semaphore。

### 线程容量与短请求隔离

```python
from concurrent.futures import ThreadPoolExecutor
from agently_stage import Stage

# 总预算四个线程，仅是示意，比例须按延迟/吞吐目标实测。
with ThreadPoolExecutor(3) as slow_pool, ThreadPoolExecutor(1) as fast_pool:
    with Stage(executor=slow_pool) as slow, Stage(executor=fast_pool) as fast:
        # slow.go(blocking_slow_call, ...)
        # fast.go(blocking_short_call, ...)
        pass
```

池必须活得比 Stage 长，先让 Stage settlement，再关闭借入的池。
`Stage(max_workers=4)` 则创建并拥有私有池；不能同时传 `executor`。
`max_concurrency` 管外部根任务，`max_pending` 管等待根任务，`max_workers`
管阻塞线程；三个参数不是同一个容量单位。

纯 Python CPU 任务若使用 `ProcessPoolExecutor`，在应用 async 函数里调用
`loop.run_in_executor(pool, module_level_function, serializable_argument)`，
再让 Stage 跟踪这个 async 函数。进程池由应用创建/关闭；函数和参数必须可序列化。
取消 await 不保证正在执行的子进程计算立即停止。不要使用
`Stage(executor=ProcessPoolExecutor(...))`，它传递的 Context 不能序列化。

### 通知与保留量是独立选择

```python
from agently_stage import Tunnel

ordinary = Tunnel(timeout=None)  # 完整回放、individual 通知
fanout = Tunnel(timeout=None, wake_mode="grouped")  # 实测高扇出后显式开启
recent = Tunnel(timeout=None, max_history=1000, wake_mode="grouped")
```

`grouped` 按每次唤醒的等待者所属 loop 分组，每个 loop 一个 callback。
同步读者仍用 Condition。所有读者仍独立按序读取，每条数据都保留在所选历史内；
关闭或失败仍先排空已接收数据。订阅者超时/取消只影响该订阅者。
对不同订阅者之间不承诺调度公平性或恢复顺序；分组可能延长单个 callback。

`max_history` 是保留量，不是生产背压。过期订阅者会收到 `TunnelLagError`，
应用需决定重新订阅或补偿。`StageStream` 承诺完整历史，不能借此静默丢帧；
其 `get()`、`async_get()` 与 success callback 返回独立列表副本。

### uvloop 与多 lane

```python
import asyncio
import uvloop  # 可选依赖，由应用安装
from agently_stage import Stage

async def main():
    async with Stage() as stage:
        return await stage.go(asyncio.sleep, 0, result=42).async_get()

uvloop.run(main())
```

此例依赖支持 `uvloop.run` 的 uvloop 版本；研究环境为 0.22.1。
它替换应用 caller loop，不宣称替换 Stage carrier 全局策略。
`Stage.set_settings("runtime.carrier_loop_count", 2)` 必须发生在首次 carrier 使用前；
该设置随后冻结，不是每次请求的调优开关。

## 兼容与证据边界

新增参数为 keyword-only，原来的四个位置参数保持有效；允许值由 Literal 和
运行时校验共同约束。0.3.8 已发布包没有 `wake_mode`，本候选不提高 Agently
依赖下限、不改包版本、不发布。Skills 对新参数明确标注候选限制。
保留裸 ctypes 分类、透明进程池、free-threaded 的已知限制，不假装已实现。

历史研究的 `audit.py` 校验的是研究时生产源码；在本候选工作区运行会因源码
已修改而失败，这是预期。验证历史请使用对应基线 `cfa1db5` 与原证据清单，
不要把新实现塞回旧实验重新生成原始结果。本目录的清单独立记录新证据。
