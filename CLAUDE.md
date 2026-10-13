# loopback 开发约定

一个工程级的终端多 agent 学习系统：带学习者从零学 Claude Code / Codex 和 agent 技术的演进。开发它本身也是一次完整的 agent 工程实践。

## 文档地图

同一内容只写一份，其他地方引用它（D25）。

| 想知道 | 看哪里 |
|---|---|
| 要做什么、做到什么程度 | `docs/requirements.md` |
| 代码现在是什么样子 | `docs/architecture.md` |
| 做到哪了、下一步做什么 | `docs/plan.md` 的「执行顺序」 |
| 为什么这样设计 | `docs/decisions.md` |
| 某个里程碑的蓝图和验收记录 | `docs/milestones/` |
| agent 技术的演进（学习材料） | `docs/agent-evolution.md` |

按要做的事去读，不用每次全读：
- 开始一个里程碑前，读 plan 的「执行顺序」和相关的决策；
- 改架构前，读 architecture.md；
- 动需求前，读 requirements.md。

## 工作方式

- 一次只做一个里程碑。开发在 `feat/core` 分支上进行。
- 只在下面四个确认点停下来，其余时候不停下来问（D26）：
  1. **方案确认**：写代码前，把蓝图写进 `docs/milestones/<里程碑>.md` 给用户看。蓝图写清楚改哪些文件、接口、数据流、测试清单，以及不做什么。
  2. **验收确认**：做完后讲解关键设计，用户按跑通标准自己跑一遍，确认后再 commit。验收记录补进同一份里程碑文件，写清计划和实际的差异，之后冻结不改。
  3. **花费确认**：调用付费 API 前（跑 eval、冒烟），先打印预计花费并设上限。
  4. **对外确认**：push、开 PR、删除仓库以外的文件，这类对外或不可撤销的动作。用户说“提交并推送”就算确认。
- 中途的小决定不停下来问，追加到 `docs/decisions.md`，验收时列出来。偏离计划时，同步修改 plan 和 requirements。
- R、D、M 编号只追加，不重排，也不复用。引用文档里的位置时写标题，不写“第几节”。
- 写“某个机制保证……”之前，要么先有测试，要么引用官方文档原文（D27 的教训）。
- commit 格式：`feat: loopback - <topic>`，文档类用 `docs: ...`。
- 选项和方案直接写在正文里，并附上推荐，不用弹窗。默认用中文回复。

## 运行与检查

```bash
uv run loopback              # 启动
uv run pytest                # 单元测试，必须全绿，不调用付费 API
uv run ruff check . && uv run ruff format --check .
```

- **不允许以任何方式读取 `.env`**，包括用 grep 读非密钥的行。
  - 需要确认配置时，看 `uv run loopback` 启动时打印的模型和接口。
  - 需要修改时，告诉用户去改哪几行。
  - `.env.example` 可以正常读写。
- 本仓库的 `.python-version` 是 3.14，由 uv 管理。pyenv 的 shim 里没有 3.14，所以不要直接用 `python`，一律用 `uv run ...`。
- 跑 eval 要花钱，跑之前要过花费确认。

## 代码约定

- 采用 src layout，代码放在 `src/loopback/`。每个模块对应一个 agent 概念，单个文件不超过约 150 行。不引入 agent 框架。
- 标识符用英文，docstring 和注释用中文。ASCII 图里只用英文。
- **注释要说明代码具体做什么，方便 code review**：
  - 每个函数用一行注释或 docstring 说明它做什么；
  - 稍长或不直观的代码块，加一行步骤注释，说明“做什么、为什么”；
  - 写代码时同步写注释，不要事后补；
  - 显而易见的代码不加注释。
- 配置只从 `Settings.from_env()` 读一次，然后显式传递。业务代码里不读 `os.environ`。
- Claude 专属的能力（缓存参数、effort、fallback、web_search、读图）一律通过 `settings.profile` 判断，保证兼容接口也能跑。
- 依赖随里程碑按需添加，用 `uv add`。

## 不变量（违反即 bug）

1. **会话是只追加的事件日志**，历史不修改、不删除。发给 API 的 messages 只是它的一个投影（D3）。
2. **每个 `tool_use` 都必须配上 `tool_result`**，包括工具抛异常、用户按 Ctrl-C 的情况。
3. **工具集在会话开始时固定**，会话中途不增减工具（为了缓存和 preserved thinking）。
4. **最小权限**（D8）：
   - 不提供 bash；
   - 文件工具只能访问 `$LOOPBACK_HOME`；
   - 读外部内容的 agent 只拿只读工具；
   - 抓来的正文当作不可信的资料处理。
5. **个人状态只写进 `$LOOPBACK_HOME`**（默认 `workspace/`，不进 git）；公共内容进 git（D6）。
6. 写状态文件用原子写（先写临时文件，再 rename），JSON 里带 `version` 字段。
