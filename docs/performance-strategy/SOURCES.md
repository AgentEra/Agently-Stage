# 来源与适用边界

2026-10-22核对。官方文档解释机制，不提供本项目的性能数字；项目性能数字只来自evidence原始结果。

- [Stage固定基线](https://github.com/AgentEra/Agently-Stage/tree/cfa1db5b9663b4559226dfab4db120adcac22b11)：Stage.py的backend与executor、_runtime.py的carrier、Tunnel.py的游标与通知。
- [Python asyncio跨线程规则](https://docs.python.org/3.14/library/asyncio-dev.html#concurrency-and-multithreading)：loop归属、threadsafe通知与blocking执行边界。
- [deque复杂度](https://docs.python.org/3.14/library/collections.html#collections.deque)：中间索引线性，支持H4复杂度假设；实测仍需规模曲线。
- [线程/进程/解释器执行器](https://docs.python.org/3.14/library/concurrent.futures.html)：独立解释器与序列化要求；不证明Stage可透明支持。
- [free-threaded Python](https://docs.python.org/3.14/howto/free-threading-python.html)：依赖兼容性与GIL启用状态须实际检查。
- [PyO3并行](https://pyo3.rs/main/parallelism)：计算在Rust执行且离开Python对象操作边界，与回调Python不同。本实验为无外部依赖C ABI探针，不等于PyO3性能。
- [Go GOMAXPROCS](https://pkg.go.dev/runtime#GOMAXPROCS)及[cgo指针规则](https://pkg.go.dev/cmd/cgo#hdr-Passing_pointers)：Go多核和跨语言内存约束。
- [Tokio blocking任务](https://docs.rs/tokio/latest/tokio/task/fn.spawn_blocking.html)：需要并行预算，已启动阻塞任务不能普通abort；本轮没有用Tokio替换Stage。
- [uvloop项目](https://github.com/MagicStack/uvloop)：替代asyncio事件循环；上游基准不作为Stage收益。

未复制私有项目规则、聊天、账号凭据或其他项目的VAD原始数据。本目录是独立Stage实验，不以VAD证据冒充Stage对照。
