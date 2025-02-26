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
uv venv --python=python3.9

# 安装开发环境依赖
uv sync --all-extras --dev

# 启动测试
uv run pytest
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

## 打包发布

完成开发和测试后，可以通过以下命令打包并发布你的工作：

```bash
# 打包, 文件会在 dist 目录下
uv build

# 发布
uv publish
```
