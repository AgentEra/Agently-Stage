# 0.3.9 实际发布与安装验收

2026-10-24（Asia/Shanghai），Agently-Stage **0.3.9 已发布并完成安装验收**。

| 对象 | 核验事实 | 来源 |
|---|---|---|
| GitHub PR | #29已合并；Linux Python3.10–3.14、lint、benchmark全部通过，无测试重跑计数 | [PR](https://github.com/AgentEra/Agently-Stage/pull/29)、[矩阵](https://github.com/AgentEra/Agently-Stage/actions/runs/40096041482) |
| 不可变标签 | v0.3.9指向b568605d65a914a0b75ad50ed79eacbc8b357ecb；属于main | [源码](https://github.com/AgentEra/Agently-Stage/tree/v0.3.9) |
| 发布CI | Python3.10/3.14验证、构建、上传全部成功 | [Publish](https://github.com/AgentEra/Agently-Stage/actions/runs/40096245953) |
| PyPI | wheel于21:01:03、sdist于21:01:04上传；版本均0.3.9 | [PyPI](https://pypi.org/project/agently-stage/0.3.9/) |
| GitHub Release | 21:01:59发布，非draft/非prerelease | [Release](https://github.com/AgentEra/Agently-Stage/releases/tag/v0.3.9) |
| Skills | Stage指导提交b81d4ae已推送公共main，七项静态验证通过；本机安装副本同步 | [指导](https://github.com/AgentEra/Agently-Skills/blob/b81d4aeb8a9498bcddba5a264a508c818f1049be/skills/agently-stage/references/performance.md) |

## PyPI 干净安装

新uv环境，Python3.10.21；通过https://pypi.org/simple无缓存安装精确版本。
包清单只有agently-stage 0.3.9。README smoke在/tmp运行，检查实际
site-packages路径、importlib.metadata版本和py.typed；性能用法示例复制到/tmp
后运行，批处理、8名grouped读者、独立线程池与借入池存活结果均符合预期。
安装包外部pyright识别Tunnel[int]/list[int]，0错误。

```sh
uv venv --python 3.10 /tmp/stage039-pypi
uv pip install --python /tmp/stage039-pypi/bin/python --no-cache \
  --index-url https://pypi.org/simple agently-stage==0.3.9
# 从仓库外运行示例，避免 examples/agently_stage 本地软链影响导入
cp examples/performance_options.py /tmp/stage039-installed-example.py
cd /tmp
/tmp/stage039-pypi/bin/python stage039-installed-example.py
```

wheel SHA256：`129b67a209fdb52d8b6ab802ded549c4a8685df9d3174ff66065c3785c2b431e`。
sdist SHA256：`a70a9e8bcb0f4cb93e480520ae8b954d71777f9120bd6497484c9ea7a172aac8`。
实际下载wheel与PyPI摘要相符；已安装19个运行时文件与标签源码逐字节相同。
本地候选wheel与发布wheel仅RECORD内容不同，其余解压内容相同；
local-distributions.json是本地候选摘要，不能当作PyPI摘要。

## 失败与证据归属修正

首次PyPI元数据已可读，但simple索引尚未同步，精确版本安装失败；原日志
保留为pypi-index-delay.txt.gz。稍后无缓存安装成功，以pypi-install.txt.gz为准。
首次安装失败后的仓库内示例仍输出成功，是examples/agently_stage软链回到
源码导致，不能算安装验证。候选阶段installed-example.txt.gz同样只能证明
源码示例效果；安装验证结论已由仓库外的PyPI复验补足。README smoke和外部
类型smoke均检查/使用真实site-packages；没有将失败改写成通过。

本次不发布Agently框架、不提高其最低依赖、不改变DevTools事件协议。
历史4.2工作区错误属于原日期的工作区证据；本次Agently集成验收采用干净dev，
4071通过、32跳过。Windows/free-threaded仍未验证，不扩展平台承诺。

完整日志以gzip无损保存于evidence/；候选覆盖矩阵见VALIDATION.md。
