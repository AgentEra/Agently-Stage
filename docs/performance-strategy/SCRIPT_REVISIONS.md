# 研究脚本维护与原始证据

2026-10-22 VPN 恢复后，Git hook 检查发现研究阶段的十个可执行 Python 脚本
尚未符合仓库格式规则。本轮只整理 import、补 future annotations、规范格式和
将 `dict(keyword=...)` 改为等价字面量；没有重新生成性能观测或改变筛选条件。

原脚本、原 README/BUILD 和原 SHA256SUMS 的逐字节压缩副本保存在
`../performance-implementation/evidence/research-originals/`，其 manifest 给出原始摘要。
`SHA256SUMS` 保持研究时的原值；它描述研究时的文件集合，不是维护后脚本的摘要。
恢复原目录时，将上述 `.gz` 解压回同名路径，然后核验原 SHA256SUMS。
原运行数据、运行时源码快照、失败记录与筛选结论继续保持原样。

当前格式化脚本已在 `cfa1db5` 源码副本上运行审计及候选/批处理测试；证据见
`../performance-implementation/evidence/research-audit-formatted.txt` 和
`research-tests-formatted.txt`。历史运行时源码校验仍需原 Stage 基线，不能在
新实现上通过重新写摘要来冒充旧证据。

完整 hook 还要求部分 JSON 的文件末尾换行，并限制单文件大小。八个研究元数据/
汇总 JSON 仅规范空白；其中 main/summary.json 改为紧凑 JSON，使其低于 500 KiB。
逐个 `json.loads` 对照已确认字段和值不变，718 个原始运行压缩档案未修改。
这些 JSON 的原字节也在 research-originals 中保存。

原字节文件名统一为 `original-<原文件名>.gz`，保留原相对父目录。恢复时按
manifest 的 key 查找对应文件，解压并去掉 `original-` 和 `.gz`。恢复后的
全部 781 个原文件逐一匹配原 SHA256SUMS。`WORKING_SHA256SUMS` 则校验当前
维护后的目录；两份清单代表不同版本，不能互换。补丁证据用 `.patch.gz`
无损保存，避免文本格式工具改变 diff 的空白上下文。
