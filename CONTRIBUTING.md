# 快速贡献指南

## 开发工具链

为了获得最佳的开发体验，我们推荐安装以下开发工具。这些工具虽然不是强制性的，但它们能显著提升你的工作效率。

### 项目管理工具 uv

[uv](https://docs.astral.sh/uv/) 是 Agently Stage 用来进行项目管理的工具，你可以从[安装指南](https://docs.astral.sh/uv/getting-started/installation/)中找到适合的安装方式。


## 本地调试

如果你想要本地调试，最佳实践是从 GitHub 上下载最新的源码来运行

```bash
git clone https://github.com/AgentEra/Agently-Stage.git
cd Agently-Stage

# 创建虚拟环境
uv venv --python=python3.10

# 安装开发环境依赖
uv sync --all-extras --dev

# 运行正确性测试（不混入性能基准）
uv run pytest --ignore=tests/test_api/test_Stage_benchmark.py

# 单独运行性能基准
uv run pytest tests/test_api/test_Stage_benchmark.py --benchmark-only
```

## 代码格式化

我们使用 Ruff 作为代码格式化工具, 并借助 pre-commit 进行提交前的格式化, 并且进行检查。

```bash
# 通过 uv 安装 pre-commit
uv tool install pre-commit

# 安装 pre-commit 钩子
uv run pre-commit install

# 检查在暂存区的文件
uv run pre-commit

# 手动运行 pre-commit 并检查所有文件
uv run pre-commit run --all-files

# 手动运行 ruff 检查
uv run ruff check .

# 手动运行 ruff 检查并输出简洁格式
uv run ruff check . --output-format concise

# 运行格式化
uv run ruff format .

```

## 打包与发布

Agently-Stage 是 Agently 的必需运行时伴随仓，但两个项目不共用版本号。Stage 的
候选版本必须先通过本仓测试，再使用候选 wheel 对 Agently 当前开发线执行跨仓校验。
只有 Stage 已发布到 PyPI 并通过干净安装验证后，Agently 才能提高最低依赖版本。

本地可以构建并检查发布产物：

```bash
# 打包, 文件会在 dist 目录下
uv build

# 检查 wheel 与 sdist 中的版本和文件
uv run python -m zipfile -l dist/*.whl
```

正式发布使用 GitHub Actions 的 `Publish` workflow。它优先读取名为
`PYPI_TOKEN` 的 repository 或 organization secret；同一个用户级 PyPI token 可以授权
`agently` 与 `agently-stage`，但 GitHub secret 必须显式对本仓可见。如果没有该 secret，
workflow 会使用 PyPI Trusted Publishing：

1. 确认 `pyproject.toml` 和 `uv.lock` 已记录候选版本。
2. 完成 Python 3.10-3.14 测试、Pyright、pre-commit 和构建校验。
3. 创建并推送不可变 tag：`v<version>`。
4. workflow 会重新校验 tag、版本、测试和构建，然后通过 OIDC 发布。
5. 对已有但尚未发布的 tag，可从默认分支手工运行 workflow，并输入不带 `v` 的版本号。
6. 发布后从 PyPI 核对版本，并在空白环境安装该版本。

如果选择 OIDC，PyPI 项目必须把 GitHub repository、workflow 文件名 `publish.yml` 和
environment `pypi` 配置为 Trusted Publisher。不得把长期 PyPI token 写入仓库、日志或
命令历史。公开 tag 不允许移动或重建；发布错误应使用新版本修正。
