# loopback

一个在终端里使用的多 agent 学习系统，用来自学 Claude Code / Codex 和 agent 技术的演进。

- **怎么学**：每天以 1 到 2 篇文章为主线，先看整体概览，再逐段精读。讲解出现在终端里，图例和动画做成 HTML 课件，在浏览器里打开。
- **旁支问题**：学习中冒出的新问题交给“助教”回答，不打断主线，也不占用主 agent 的上下文。
- **效果可度量**：自带 evals，“讲得好不好”用数据说话，不靠感觉。

> 当前状态：**M3a 可用版**：终端里逐节学习、项目自学、轨迹查看。路线图见 [docs/plan.md](docs/plan.md)，设计决策见 [docs/decisions.md](docs/decisions.md)，学习材料见 [docs/agent-evolution.md](docs/agent-evolution.md)。

## 快速开始

需要 [uv](https://docs.astral.sh/uv/)，Python 3.14 由 uv 自动管理。

```bash
uv sync                      # 安装依赖
cp .env.example .env         # 填入 ANTHROPIC_API_KEY
uv run loopback              # 开始学习：输入 next 开始或继续，/help 查看命令
uv run loopback trace        # 查看最近一次会话的轨迹
```

想用 DeepSeek 等 Anthropic 兼容接口，在 `.env` 里设置 `ANTHROPIC_BASE_URL` 和 `MODEL_ID` 即可，见 `.env.example`。

## 开发

```bash
uv run pytest                # 单元测试，不调用付费 API
uv run ruff check .          # lint
uv run ruff format .         # 格式化
```

## 目录

| 路径 | 内容 |
|---|---|
| `src/loopback/` | 源码：配置、agent 循环、工具、渲染等 |
| `tests/` | 单元测试，用 FakeLLM，不花钱 |
| `docs/` | 计划、设计决策、学习材料 |
| `workspace/` | 个人状态：进度、课件、日志等。不进 git，路径可以用 `LOOPBACK_HOME` 修改 |

## License

MIT
