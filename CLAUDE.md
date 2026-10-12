# loopback 开发约定

一个工程级的终端多 agent 学习系统。完整计划在 `docs/plan.md`，设计决策在 `docs/decisions.md`。动手前先读这两份。

## 工作方式

- 按 `docs/plan.md` 第 4 节的里程碑推进，**一次只做一个**。做完后讲解关键设计，停下来等用户确认，确认后再 commit。
- commit 格式：`feat: loopback - <topic>`，文档类用 `docs: ...`。开发在 `feat/core` 分支上进行。
- 选项和方案直接写在正文里给出，并附上推荐，不用弹窗。默认用中文回复。
- 遇到新的设计决策，追加到 `docs/decisions.md`。如果偏离了计划，同步修改 `docs/plan.md`。

## 运行与检查

```bash
uv run loopback              # 启动
uv run pytest                # 单元测试，必须全绿，不调用付费 API
uv run ruff check . && uv run ruff format --check .
```

- **不允许以任何方式读取 `.env`**（包括 grep 非密钥的行）。需要确认配置时，看 `uv run loopback` 启动时打印的模型和接口；需要修改时，告诉用户去改哪几行。`.env.example` 可以正常读写。
- 本仓库的 `.python-version` 是 3.14，由 uv 管理。不要直接用 `python`，因为 pyenv 的 shim 没有 3.14。一律用 `uv run ...`。
- 跑 eval 会花钱：运行前先打印预计花费，等用户确认后再跑。

## 代码约定

- src layout：代码放在 `src/loopback/`。每个模块对应一个 agent 概念，单个文件不超过约 150 行。不引入 agent 框架。
- 标识符用英文；docstring 和注释用中文。ASCII 图里只用英文。
- **注释要说明代码具体做什么，方便 code review**：每个函数用一行注释或 docstring 说明它做什么；稍长或不直观的代码块，加一行步骤注释，说明“做什么、为什么”。写代码时同步写注释，不要事后补。显而易见的代码不加注释。
- 配置只从 `Settings.from_env()` 读一次，然后显式传递，不在业务代码里读 `os.environ`。
- Claude 专属能力（缓存参数、effort、fallback、web_search、读图）一律通过 `settings.profile` 判断，保证兼容接口也能跑。
- 依赖随里程碑按需加，用 `uv add`。

## 不变量（违反即 bug）

1. **会话是只追加的事件日志**，不修改、不删除历史。发给 API 的 messages 只是它的一个投影（D3）。
2. **每个 `tool_use` 都必须配上 `tool_result`**，包括工具抛异常、用户按 Ctrl-C 的情况。
3. **工具集在会话开始时固定**，会话中途不增减工具（为了缓存和 preserved thinking）。
4. **最小权限**：不提供 bash；文件工具只能访问 `$LOOPBACK_HOME`；读外部内容的 agent 只拿只读工具；抓来的正文按不可信资料处理（D8）。
5. **个人状态只写进 `$LOOPBACK_HOME`**（默认 `workspace/`，不进 git）；公共内容进 git（D6）。
6. 写状态文件用原子写（先写临时文件再 rename），JSON 里带 `version` 字段。
