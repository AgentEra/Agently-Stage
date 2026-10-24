# 落地验证报告

日期：2026-10-22，macOS arm64；Stage 基线 `cfa1db5b9663b4559226dfab4db120adcac22b11`，
候选分支 `feature/performance-strategy-evaluation`。这是模型无关的进程内基础设施测试，
没有模型质量或业务能力结论。原测量档案不改写；本轮是候选代码的独立复验。研究脚本/JSON 的格式维护
及原字节恢复见 performance-strategy/SCRIPT_REVISIONS.md。

## 验证方法与观测

`compare.py` 在每次运行启动独立 Python 3.10.21 进程，使用相同负载，五轮交替
基线/候选次序。8 个回放配置 × 2 变体 × 5 轮，加 9 个广播配置 × 3 变体 ×
5 轮，共 **215 次**，全部返回完整正确结果。grouped 与本轮 individual 默认比较，
默认与基线比较，避免将存储收益算成通知收益。每次 stdout、stderr、命令、版本、
源码路径与 SHA256、延迟数组保存在 `evidence/performance/*.json.gz`。

| 场景 | 基线或默认耗时中位数 | 候选中位数 | 逐轮改善中位数 | 改善轮数 |
|---|---:|---:|---:|---:|
| 10 万项无界同步回放 | 64.781 ms | 25.500 ms | 60.1% | 5/5 |
| 10 万项无界异步回放 | 69.110 ms | 31.822 ms | 51.8% | 5/5 |
| 1000 项无界同步回放 | 0.313 ms | 0.317 ms | -0.4% | 2/5 |
| 1 万项无界同步回放 | 2.917 ms | 2.642 ms | 8.7% | 5/5 |
| 32 读者、同 loop 连续广播：grouped | 24.925 ms | 19.797 ms | 20.4% | 5/5 |
| 单读者、同 loop 定速广播 P99：grouped | 0.249 ms | 0.381 ms | -60.1% | 1/5 |

结论：保留无界索引优化默认；小历史近似持平，不夸大为普遍显著收益。
通知合并存在明确高扇出收益和低扇出反例，因此只显式启用。对实际生产负载仍需
看 P99、吞吐和 CPU，不按人数阈值自动开关。有限样本不是统计显著性证明。
完整均值以外的中位数、min/max、逐轮值、配对百分比见
[全表](evidence/performance/TABLES.md) 与 [summary.json](evidence/performance/summary.json)。

回放 `wall_s` 只计消费，`fill_s` 单列；`cpu_s` 包含填充和消费。
广播定速 P99 从计划产生时刻起算，包括生产调度迟到，不仅是队列驻留。
异步回放还含事件循环创建成本。主机没有操作系统级隔离，调度噪声仍存在；
固定交替次序减少但不能消除漂移。并未重新跑 H1/H2/H3/H6/H8/H9 的所有历史负载，
因为这些策略本轮只补充既有接口用法，没有修改其运行时代码。

## 合同覆盖

| 合同 | 证据与结果 |
|---|---|
| 同/跨线程、两个 owner loop、取消/close/fail、超时、失效 loop、非法参数和旧位置参数 | `modes-310.txt`，9 passed |
| grouped 下复用原 Tunnel API、races 和 StageStream 契约 | `grouped-contracts-310.txt`，35 passed |
| Python 3.10 | `stage-310.txt`，230 passed、1 skipped（显式 task context 需 3.11） |
| Python 3.11 / 3.12 / 3.13 / 3.14 | 对应 `stage-*.txt`，各 231 passed |
| 官方 CI 的 benchmark 文件 | 正确性矩阵按 CI 排除；性能由本轮独立对照覆盖，不把 benchmark 门槛当正确性 |
| 类型检查 | `pyright-tracked.txt`，全部受版本管理的源码/测试/示例加新增文件，0 errors |
| lint / format | `ruff.txt`，通过 |
| 推荐示例 | `example-final.txt`，实跑输出回填源码注释，已纳入五版本示例测试 |
| Skills | 七个 `skills-*.txt` 校验通过；新能力标明候选限制，安装副本同步对应段落 |
| Agently 4.2 当前工作区受影响路径 | `agently-affected.txt`，34 passed；预期 close-timeout warning 一条 |
| Agently 当前工作区全套 | `agently-full.txt`，22 个收集错误；原 Stage 基线 `agently-current-baseline-collection.txt` 重现同一组 22 个错误 |
| Agently dev 干净快照全套 | `agently-dev-full.txt`，4071 passed、32 skipped、198 warnings，203.92 秒 |

未把当前 4.2 工作区全套标为通过。其已有未提交重构缺失 AgentTask 等模块，
与本次 Stage 候选无关；未修改或清理这些他人工作。干净 dev 快照使用
`b385ab2b8abfaf583d79ddbb1d5218646610a9da`。候选 wheel 安装到独立 target，
Agently 依赖复用既有 Python 3.14.7 开发环境；`wheel-identity.txt` 证明实际
导入来自候选 wheel，不是 Stage 工作区。本轮不是最小依赖 clean-install 发布验证。

完整目录 pyright 扫描还发现 ignored 的 `examples/test.py` 两个既有错误，
记录在 `pyright.txt`；没有为消除它们修改本地试验文件或放宽项目规则。
Git hook 初始化访问 GitHub 超时；`precommit.txt` 和 `github-connectivity.txt`
保留事实。这些是恢复前的失败记录。VPN 恢复后完整 pre-commit 已通过，
见 `precommit-final.txt`；没有绕过 hook。
VPN 恢复后重新执行 hook，见后续通过记录；本轮不合并、不发布、不提高依赖下限。

## 复现与审计

```sh
# 从 Stage 仓库执行；输出目录和基线目录请用新的路径。
mkdir -p /tmp/stage-baseline-replay
git archive cfa1db5 agently_stage | tar -x -C /tmp/stage-baseline-replay
python docs/performance-implementation/compare.py /tmp/stage-baseline-replay "$PWD" /tmp/stage-recheck
python -m pytest -q tests --ignore=tests/test_api/test_Stage_benchmark.py
python docs/performance-implementation/check_modes.py grouped
PYTHONPATH=. python examples/performance_options.py
```

对每个 Python 3.10–3.14 环境运行同一 pytest 命令（需 pytest）；实际解释器和
命令见 `evidence/matrix.json`。`evidence/source-manifest.json` 与压缩源码快照
固定实测实现，`SHA256SUMS` 固定本目录证据。性能记录的 Tunnel 源码 SHA256
已与最终实现核对一致。wheel 身份和构建/安装日志单独记录，0.3.8 元数据仅为
本地候选，不代表发布了同版本新制品。

历史 `docs/performance-strategy/SHA256SUMS` 与本轮独立；历史 audit 必须配合
原基线运行。不得在新源码上复写旧实验数据以制造“旧实验通过”。

## 对账与交付范围

- E1–E4：既有研究已完成，718 个原始运行压缩档案、失败轨迹和原 SHA256SUMS 保持原样；
  十个脚本及八个 JSON 仅作格式维护，原字节保存在 research-originals，
  781 个原文件全部可恢复并逐一通过原摘要；审计718档案、14项候选测试复验通过。
- E5：H1–H9 默认／可选／暂缓逐项确定；改变的是机制实现与指导，不是业务语义。
- E6：实现、docstring、中文指南、实跑示例及 Skills 对齐完成。
- E7：五版本 Stage 矩阵、215 次对照、七项 Skills、类型/lint、Agently dev 全套完成。
  当前 4.2 脏工作区完整套件存在已复现的基线错误，不能替代为通过结论。
- Spec 对账完成，保留 planned 状态表示“分支候选，未合入/发布”。
- Compatibility：新增 keyword-only 参数、没有依赖/包版本变动，旧参数和结果合同保留。
- DevTools：没有 RuntimeEvent、ObservationEvent 或 lineage 改动，无需同伴代码变更。
- Skills 使用独立集中 worktree，保留原仓库其他脏文件；安装副本只同步本轮新增指导。
- VPN 恢复后 Git hook 已恢复执行；Skills 指导已本地提交 `28d16e3`。
  Stage 提交记录见 Git 与最终 RioWork 交付；不合并、不发布，未绕过 Git hook。
