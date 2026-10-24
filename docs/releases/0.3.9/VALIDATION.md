# 0.3.9 发布验收依据

日期：2026-10-24（Asia/Shanghai）。实现来源 aeb7ea0；发布基线
cfa1db5（远端 main 核验）；本次不改变 agently_stage 运行时源码。

## 从合同到证据

| 合同 | 验证类别与证据 | 结论/边界 |
|---|---|---|
| 无界/有界回放、独立读者、lag、close/fail、位置参数兼容 | tests/ 内原有合同与新增 test_tunnel_modes；pytest-310/314 | 3.10：230通过/1跳过；3.14：231通过 |
| grouped 跨线程/跨loop通知、取消和关闭loop | 新增9项模式测试；原35项grouped合同历史证据 | 无运行时变动，复用有效历史证据 |
| 稳定默认与负载依赖的显式配置 | 原215次性能对照、示例、docstring及中文用法指南 | 源码摘要逐一匹配；不重跑并伪造新性能结论 |
| Python兼容矩阵 | 本次3.10.21/3.14.7；历史3.11–3.13全套 | 中间版本历史有效；Linux由发布CI再次验证 |
| 公共类型 | 干净源码快照pyright；已安装wheel外部类型解析 | 0 errors；Tunnel[int]和list[int]被正确识别；py.typed存在 |
| 可安装性与模型无关效果 | 新uv环境只安装wheel后运行README代码和performance_options.py | 版本0.3.9；仓库内示例有软链，安装效果以PUBLICATION中的仓库外PyPI复验为准 |
| Agently集成 | 干净dev b385ab2，以PYTHONPATH指向候选wheel独立target | 4071通过、32跳过、198警告，216.57秒；不用4.2脏工作区代替基线 |
| Skills | 在公共main f90a51a上迁移Stage指导，七项静态校验 | 通过；0.3.9门槛明确；不覆盖其他指导 |
| DevTools/依赖范围 | owner及公开协议审查 | 无事件、lineage变化；无须发布DevTools或提高Agently最低依赖 |
| 延期项 | 指南/研究中的Go/Rust调度、透明进程/解释器、free-threaded | 不在本版能力承诺中 |

## 可复现命令与失败修正

从干净源码检出执行：

```sh
uv sync --dev --locked --python 3.10
uv run pyright agently_stage tests examples
uv run pytest -q --ignore=tests/test_api/test_Stage_benchmark.py
uv run pre-commit run --all-files
uv build
```

初次运行发现默认pytest把docs研究测试也收集，缺少本机Go/Rust .dylib，
242通过/2失败/1跳过。失败日志保留为preflight-research-collection-failure。
根因是研究目录加入仓库后未限定默认发现范围；pyproject的testpaths设为tests，
没有删除/skip运行时测试或研究测试。研究测试有独立BUILD.md和显式运行入口。
配置修正后CI同形命令在3.10和3.14通过。benchmark文件沿既有CI约定排除；
其性能职责由独立对照承担。

源码检查使用git受控文件的干净快照，避免主工作区ignored实验文件污染；
无关本地实验文件保留。安装smoke在/tmp下运行，实际包路径见日志；
先验证只含Stage的最小环境，再额外安装pytest做3.14回归。
安装测试/类型smoke源码、候选构建日志、源码摘要、测试日志均在evidence/。
测试工具版本以uv.lock及日志为准，pyright 1.1.411。
Agently完整回归复用其开发环境依赖，只替换Stage wheel；不把该结果
称为Agently最小依赖安装测试。Stage包无运行时第三方依赖。

## 发布前后事实分离

此文件记录候选验收。实际发布与安装复验已完成，见[PUBLICATION.md](PUBLICATION.md)。标签触发的Linux CI、PyPI包摘要、GitHub Release和
发布后干净安装须以公开CI/PyPI结果及后续PUBLICATION.md记录为准；
本地构建成功不代表发布成功。Windows/free-threaded未在本轮验证。

历史研究与实现报告保持原日期、原版本及原失败状态；其中“未发布”描述
当时的事实。当前用法以0.3.9说明为准。

完整pre-commit通过；benchmark smoke两项通过。证据文本以.txt.gz无损保存，
防止格式钩子改写原日志；可用gzip -dc读取。SHA256SUMS覆盖本发布记录。
