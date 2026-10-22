# 构建、执行与复算记录

仓库根目录执行；测量解释器 `/opt/miniconda3/envs/3.10/bin/python`（3.10.21），pytest 8.4.2、psutil 7.2.2、uvloop 0.22.1。机器信息和生产源码哈希以每批manifest为准。测量使用本机已有安装，没有更换测量环境。交付校验另在临时虚拟环境安装pre-commit，以运行仓库既有提交门禁（原钩子记录的旧环境已不存在）；不影响已完成的性能测量。

## 原生库

- `/Users/moxin/.cargo/bin/rustc --version`：`rustc 1.99.0 (b940084d7 2026-09-28)`。
- `/opt/homebrew/bin/go version`：`go version go1.27.0 darwin/arm64`。
- macOS 26.5.1，build 25F80，Apple M5 Pro，15核，48GiB。

```sh
mkdir -p docs/performance-strategy/build
/Users/moxin/.cargo/bin/rustc --crate-type cdylib -C opt-level=3 docs/performance-strategy/native.rs -o docs/performance-strategy/build/rust.dylib
/opt/homebrew/bin/go build -buildmode=c-shared -o docs/performance-strategy/build/go.dylib docs/performance-strategy/native.go
```

不引入第三方Rust/Go库。动态库和Go生成的头文件留在ignored的`build/`，交付源代码及编译命令，不提交平台二进制。C ABI标量为uint64，完整算法由Python参考实现与两种原生实现交叉检查。未进行ABI内存安全审计。

## 实际执行

下列命令中的`python`指上述3.10解释器。输出目录已存在时不要再次使用相同`--out`；复现要换新目录。

```sh
python docs/performance-strategy/suite.py --out docs/performance-strategy/evidence/preflight --repeats 1 --smoke
python -m pytest -q tests --ignore=tests/test_api/test_Stage_benchmark.py
python -m pytest -q docs/performance-strategy/test_candidates.py
python docs/performance-strategy/capabilities.py
python docs/performance-strategy/suite.py --out docs/performance-strategy/evidence/main --repeats 5
# 上一条为历史裸ctypes版本；遇到已留证的失败后统一加普通Python wrapper。
python docs/performance-strategy/suite.py --out docs/performance-strategy/evidence/native-adapter --repeats 5 --native-only
python docs/performance-strategy/check_contracts.py chunk
python docs/performance-strategy/check_contracts.py grouped
python docs/performance-strategy/check_contracts.py local
python -m pytest -q docs/performance-strategy/test_batch_contracts.py
python docs/performance-strategy/archive_raw.py
python docs/performance-strategy/analyze.py docs/performance-strategy/evidence/main
python docs/performance-strategy/analyze.py docs/performance-strategy/evidence/native-adapter
python docs/performance-strategy/audit.py
```

Python3.14能力探针使用本机已有的3.14.8虚拟环境执行同一`capabilities.py`，输出完整保存在`evidence/capabilities-314.json`；仅依赖标准库和本地Stage。未用此环境测性能，也没有安装free-threaded解释器。

基线唯一跳过项为`test_task_factory_accepts_explicit_context`：Python3.10没有3.11引入的asyncio `context=`参数；该skip是既有测试标记。未以跳过掩盖候选失败。

## 证据保护与判定

`archive_raw.py`在读回解压字节逐一相等后才删除未压缩副本；`raw-index.json`保存两份摘要。718份档案包含8次预检和710次正式执行。原始失败保留，不补写为通过。分析脚本增加gzip读取支持前的版本也在原生批次source内保留，其摘要与manifest一致。

`audit.py`核验源文件或批次source副本的全部manifest哈希，核验重复编号唯一性、有效样本正确性标志、128配置与640样本的最终选择。数值重算通过不等于生产性能复现；机器负载、编译器或代码变化后须重新运行性能矩阵。

历史Python源码使用`source/*.py.gz`无损封存，避免后续格式化改写测量时的准确文件；解压后的SHA-256须与manifest相同。测量时的准确执行版本始终以批次source为准。

提交门禁尝试未完成：临时环境成功安装pre-commit 4.6.2，但原有配置初始化`https://github.com/pre-commit/pre-commit-hooks`时连接无响应，独立HTTPS检查也在12秒超时。本会话停止自己的挂起抓取，保留[初始化记录](evidence/precommit-unavailable.txt)，没有绕过门禁提交。因此本轮工作区文档未提交Git；以文件SHA-256清单和固定归档保存完整来源。该限制不影响此前完成的实验、测试和数据复算，也不应表述为提交检查通过。
