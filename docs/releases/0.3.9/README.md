# Agently-Stage 0.3.9

0.3.9 优化长历史回放，并提供显式的多读者通知合并。兼容 Python 3.10+，
保留 0.3 系列公共语义，无新增运行时依赖。

```shell
python -m pip install --upgrade 'agently-stage==0.3.9'
```

原有调用无需修改，默认通知策略保持不变：

```python
from agently_stage import Tunnel

channel = Tunnel()  # 默认 individual，0.3.8 调用可继续使用
channel.put(1)
channel.close()
assert list(channel) == [1]

# 0.3.9 新增：同一 loop 上等待的读者较多时，显式评估该选项
channel = Tunnel(wake_mode="grouped")
```

| 范围 | 变化 | 推荐用法 | 兼容性与代价 | 证据 |
|---|---|---|---|---|
| 无界回放 | 内部改用 list 常数索引；有界仍为 deque | 默认使用，无需开关 | 保留完整历史，内存 O(N)；有界慢读者仍可能 lag | [正确性与性能](../../performance-implementation/VALIDATION.md)、Tunnel/StageStream 合同测试 |
| 读者通知 | 新增 keyword-only wake_mode | 默认 individual；高扇出可测 grouped | 无延迟窗口、不合并数据、不丢数据；少读者或尾延迟敏感场景可能变慢 | tests/test_runtime/test_tunnel_modes.py、215 次对照 |
| 线程与批处理 | 明确现有配置的推荐边界 | 单 lane 默认；显式分组、线程预算和池隔离 | 不自动扩线程、不自动合并任务；隔离可能增加总耗时 | [指南](../../performance-implementation/README.md)、examples/performance_options.py |
| 暂缓 | Go/Rust 调度重写、透明进程/解释器池、free-threaded 自动策略 | CPU 密集工作由应用建立明确并行边界 | 本版不声称提供这些后端 | [H1–H9 研究](../../performance-strategy/REPORT.md) |

## 性能依据与适用范围

复用 2026-10-22 macOS arm64 的独立进程交替对照：10 万项无界同步/异步
回放配对改善 60.1% / 51.8%（各 5/5）；32 同 loop 等待读者的非定速负载，
grouped 相对 individual 配对改善 20.4%（5/5）。单读者定速 P99 有退化反例，
因此 grouped 保持可选。这是特定硬件和负载的观测，不是通用性能保证。
原脚本、原始结果、失败记录及校验清单均保留；本次发版未改变运行时代码。

## 发布验收

发布验证及覆盖矩阵见 [VALIDATION.md](VALIDATION.md)。
Agently 既有 >=0.3.8,<0.4.0 支持范围允许本版；使用新参数须 >=0.3.9。
本次发布独立 Stage 包，不提高 Agently 的依赖下限，不改变 RuntimeEvent 或
DevTools 协议。历史 4.2 收集错误的记录不代表当前分支状态，不能据旧日志
断言当前 4.2 全套通过或失败。
