# Agently-Stage 性能策略研究

本目录保存2026-10-22的逐命题实验、代码、原始证据和策略筛选。它是研究材料，不是已经合入的生产优化，也不是模型应用示例或生产容量承诺。

- [实验合同与命题](PLAN.md)：测试前的范围、判定标准和H1–H9矩阵。
- [完整中文筛选报告](REPORT.md)：结论、逐项对照、反例、适用条件和未验证项。
- [构建与执行记录](BUILD.md)：编译环境、准确命令与正确性检查。
- [机制来源](SOURCES.md)：官方文档及固定Stage基线。
- `evidence/`：每次测量、环境清单、正确性日志、能力探针及排除记录。
- `bench.py` / `suite.py` / `analyze.py`：单配置执行、随机化五轮运行和复算。
- `candidates.py`：仅研究使用的回放存储与唤醒候选，不修改生产包。
- `native.rs` / `native.go`：同算法C ABI与Python回调探针，不是完整Stage改写。
- `test_candidates.py` / `capabilities.py`：候选正确性、版本和executor边界验证。

最终采用128配置各5轮的640份有效样本；正式执行710次，20次失败完整保留。逐配置统计在各次运行的 `TABLES.md` 中，原生组以 `native-adapter/` 为准。

## 复现原则

使用固定Stage基线和manifest的Python/依赖版本。先运行候选检查，再运行性能；不同实验套件不要同时运行。`suite.py`要求新的输出目录，不覆盖或悄悄复用历史结果。预检不进入正式统计。

```sh
# 在Agently-Stage仓库根目录；Python3.10+，安装pytest、psutil、uvloop
mkdir -p docs/performance-strategy/build
rustc --crate-type cdylib -C opt-level=3 docs/performance-strategy/native.rs -o docs/performance-strategy/build/rust.dylib
go build -buildmode=c-shared -o docs/performance-strategy/build/go.dylib docs/performance-strategy/native.go
python -m pytest -q docs/performance-strategy/test_candidates.py
python -m pytest -q docs/performance-strategy/test_batch_contracts.py
python docs/performance-strategy/check_contracts.py chunk
python docs/performance-strategy/check_contracts.py grouped
python docs/performance-strategy/check_contracts.py local
python docs/performance-strategy/suite.py --out docs/performance-strategy/evidence/reproduction-new --repeats 5
python docs/performance-strategy/analyze.py docs/performance-strategy/evidence/reproduction-new
```

本轮构建和库名面向macOS。Linux/Windows须调整动态库后缀与编译环境，然后重新采样，不能把本机数据直接作为跨平台结论。`evidence/main/source/`保留首轮准确源码；后续调整使用独立证据目录和manifest，不覆盖初轮失败。

复算已归档证据（无需编译或运行性能测试）：

```sh
python docs/performance-strategy/analyze.py docs/performance-strategy/evidence/main
python docs/performance-strategy/analyze.py docs/performance-strategy/evidence/native-adapter
python docs/performance-strategy/audit.py
```

`analyze.py`同时读取JSON与无损gzip；`audit.py`针对本次固定两批运行核验718份档案（含8份预检）、源码摘要和最终640份样本覆盖，要求本地生产源码仍与基线一致。`main/summary.json`的`complete=false`真实反映初轮20次失败，不应改为true；完整性以两批合并选择的`audit.json`为准。

历史`source/`用于追溯，不应在它的嵌套路径直接启动脚本（脚本按仓库相对位置导入包）。要复现初轮裸ctypes失败，应在另一个固定基线工作区将历史脚本恢复到`docs/performance-strategy/`对应位置；日常复现使用本目录的适配后脚本。

所有性能负载为可重放的确定性基础设施负载，模型调用/远程工具调用均为0。文档不得把休眠等合成等待称为真实网络或SDK实测。

研究脚本在提交前的格式维护及原字节恢复方法见 [SCRIPT_REVISIONS.md](SCRIPT_REVISIONS.md)。
