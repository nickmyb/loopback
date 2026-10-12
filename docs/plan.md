# loopback：自学 Claude Code / Codex 的多 agent 终端学习系统

> 定稿：2026-10-12。计划有变动时直接改这份文档，并在 `docs/decisions.md` 里记下原因。

## Context

**目标**：做一个**工程级**（不是 demo）的终端学习 agent。它带着学习者从零学到能拿下 agent 研发岗位，开发它的过程本身就是一次完整的 agent 工程实践。

**节奏**：**先把主体（core）做扎实**。主体之外的细节和体力活，先写清楚“在哪里补、补什么、怎么补”，等 core 完成后再做。

**需求清单**（来自 6 轮讨论，下文第 3 节和附录 B 有细节）

| # | 需求 |
|---|---|
| R1 | 终端对话；图例和动画放在 HTML 课件里，自动在浏览器打开 |
| R2 | 每天 1 到 2 篇为主线：先出概览，再交互式逐段讲解，最后出总结；进度存盘，可以跨天续学 |
| R3 | 旁支问题交给助教，主 agent 的上下文零污染。问题分三类：术语、文中链接详解、材料之间的关联 |
| R4 | 讲解越简单越好（大白话规则），多用图 |
| R5 | 有一套从零到 expert 的分级材料；演进清单要保持更新 |
| R6 | 添加材料要方便，以 Chrome 书签文件夹为主，体验类似阅读清单 |
| R7 | 大厂真实面试题：来源可追溯，分必刷、常见、拓展三档，参考答案基于学过的材料 |
| R8 | **Evals 是重点**：课程里有 evals 主线；loopback 自身的效果要可度量、可信 |
| R9 | 可以自我进化，但只在 eval 护栏之内 |
| R10 | 不绑死 Claude，DeepSeek 等兼容接口也能跑 |
| R11 | 工程级：架构、测试、错误处理、安全、可观测性都要有，见第 2 节的清单 |

**已经确定的技术选型**：
- Python **3.14.8**，用 uv 管理；
- 官方 `anthropic` SDK，不用任何 agent 框架；
- `.env` 沿用 `ANTHROPIC_API_KEY` / `MODEL_ID` / `ANTHROPIC_BASE_URL`；
- 默认模型是 `claude-opus-5-5`。

**plan mode 期间已经写入的文件**（已处理）：
- `docs/plan.md`：审批后用本计划覆盖；
- `pyproject.toml`：Python 版本要改成 3.14；
- 3 个 memory 文件。

---

## 1. 架构

```
 you ──REPL(cli.py)──┬─ next / free text ──> TEACHER   (main session)
                     ├─ ?question ─────────> TA        (side session per section)
                     └─ /commands ─────────> harness code (progress, cost, ...)

 every agent = AgentSpec(prompt file, tool set, model, effort)  run by the SAME agent_loop
 agent_loop(session, spec, llm):
     stream request ─> append assistant event ─> run tools ─> append tool_result events ─> repeat
 session = append-only event log (JSONL)  ──projection──>  messages sent to the API
 state   = files under $LOOPBACK_HOME (progress, library, lessons, feedback, transcripts)
```

**三个底层决策**：它们事后很难再改，所以必须在 core 阶段就定下来。

1. **会话就是只追加的事件日志**，用 API 的 messages 只是它的一个投影。这个思路来自附录 A.3 的 Managed Agents 一文：会话不等于上下文窗口。好处有四个：
   - 天然满足 preserved thinking 和 prompt 缓存的要求；
   - 中断后可以恢复；
   - eval 和反思员都直接读事件日志；
   - 压缩只是换一种投影方式，不需要改写历史。
2. **LLM 通过接口注入**，定义为 `LLM` protocol。生产环境用 Anthropic client，测试时用 `FakeLLM` 按剧本返回预设响应。这样整个 loop 和各个 agent 都能在不花钱的单元测试里跑。
3. **Prompt 和 skill 都放在文件里**，每次请求都记下它们的 hash。这样 eval 结果和进化记录才能对应到具体是哪个 prompt 版本。

**目录**：采用 src layout，并通过 `uv run loopback` 启动。

```
loopback/
├── pyproject.toml  uv.lock  .python-version(3.14)  .env.example  .gitignore  CLAUDE.md  README.md
├── .github/workflows/ci.yml          # ruff + pytest (no paid calls)
├── src/loopback/
│   ├── config.py      # typed Settings from env/.env + capability PROFILE (official/vision/server_tools)
│   ├── llm.py         # LLM protocol, Anthropic client factory, request builder (caching/effort/fallback by PROFILE)
│   ├── session.py     # append-only event log + messages projection + invariants
│   ├── tools.py       # Tool registry: name, schema, handler, read_only; dispatch (exception -> is_error)
│   ├── loop.py        # agent_loop: streaming, stop_reason handling, usage accounting
│   ├── agents.py      # AgentSpec + roster (teacher, ta, ask-subagent)
│   ├── skills.py      # two-layer SkillLoader
│   ├── extract.py     # HTML/markdown -> clean markdown (dense container + markdownify)
│   ├── materials.py   # markdown -> sections (+links L1.., images I1..), heading paths
│   ├── library.py     # fetch + cache in $LOOPBACK_HOME/library/<id>/; outline; wrapped section text
│   ├── curriculum.py  # curriculum (validated, searchable) + progress.json
│   ├── learning.py    # teacher tools: find_material, curriculum_status, fetch_material, read_section, update_progress
│   ├── store.py       # atomic JSON/JSONL writes, schema version field
│   ├── render.py      # lesson pages: template, nav, index, render_lesson tool
│   ├── blocks.py      # content blocks -> safe HTML (markdown escape, mermaid lint)
│   ├── svg.py         # SVG sanitize/validate (no script/external refs, XXE-safe)
│   ├── feedback.py    # 1-5 ratings per section -> feedback.jsonl
│   ├── trace.py repo.py repl.py mcp_server.py   # M3a/M3c: trace, self-study, REPL, Claude Code front-end
│   ├── files.py       # workspace-confined file tools
│   ├── pricing.py     # usage -> USD estimate, cache hit rate
│   └── cli.py         # REPL + routing + slash commands
├── src/loopback/prompts/*.md        src/loopback/skills/*/SKILL.md   (package data, versioned + hashed)
├── src/loopback/templates/lesson.html  # CSS tokens, light/dark, mermaid (+fallback), steps player
├── src/loopback/data/curriculum.yaml # shared content (in git), 72 items: L0 docs + evolution list
├── evals/{run.py,graders.py,judge.py,report.py,suites/...}
├── tests/                           # FakeLLM-based unit tests, golden sectioning, render snapshots
└── docs/{plan.md,decisions.md,agent-evolution.md}
```

---

## 2. 工程化清单：哪里补什么、怎么补、什么时候补

- **core**：现在就做。要么事后很难改，要么是主体能不能用的前提。
- **后补**：怎么做已经想清楚了，等 core 完成后再补，基本是体力活。

| 领域 | 工程级要求 | 怎么做 | core（现在就做） | 后补（体力活） |
|---|---|---|---|---|
| **架构与接口** | 模块边界清晰，可以替换、可以测试 | 用 `LLM` protocol、`Tool` 注册表、`AgentSpec`、事件日志 `Session` 这几个接口 | 全部接口 | — |
| **配置** | 有类型、有默认值、可以校验，能按服务商切换能力 | 用 `Settings` dataclass 读 env；用 `PROFILE` 决定开关 | Settings 加 PROFILE | 配置校验的报错提示做得更友好 |
| **错误处理** | 每类错误都有明确去向 | 分类处理：<br>• API 错误：可重试的交给 SDK 自带的退避重试，不可重试的直接报给用户；<br>• `refusal` 和 `max_tokens` 截断：显式处理；<br>• 工具异常：返回 `is_error` 让模型自己修正；<br>• 抓取失败：降级为手动提供 `source.md` | 错误分类；**不变量：每个 tool_use 都必须配上 tool_result**，Ctrl-C 中断时也要补上 | 覆盖所有边界情况；网络抖动时的友好提示 |
| **状态持久化** | 不能写坏文件，能升级数据格式 | 原子写：先写临时文件再 rename；JSON 里带 `version` 字段 | 原子写和 version 字段 | 格式迁移脚本；单实例文件锁 |
| **安全** | 最小权限；外部内容一律当作不可信 | • **不提供 bash 工具**，文件工具限制在 `$LOOPBACK_HOME` 里，并检查路径穿越；<br>• 抓来的正文用定界符包起来，并声明“这是资料，不是指令”；<br>• 读外部内容的 agent 只拿只读工具；<br>• HTML 转义；SVG 去掉 script、`on*` 属性、`foreignObject` 和外部引用 | 以上全部，规则都很短 | 课件加 CSP；做 prompt 注入的红队用例 |
| **可观测性** | 每次调用都能追溯 | 事件日志就是 transcript；每次调用记录 usage、model、延迟、prompt hash；`logging` 输出结构化日志；`/cost` 命令 | 事件日志、usage、`/cost` | OpenTelemetry tracing；成本日报 |
| **测试** | 不花钱就能验证核心逻辑 | 用 `FakeLLM` 按剧本测：tool 配对、错误路径、助教隔离、恢复；切节用 golden 文件测；渲染用快照测 | 核心路径的测试 | 覆盖率补到 80% 以上；属性测试 |
| **Evals** | 效果可度量、可信，详见附录 B.6 | runner 支持多次重复加置信区间；基础设施错误单独记录；oracle 和 null 两条基线；评审先用人工标注校准；报告带完整轨迹 | runner、评分器、teacher 和 ta 两个小套件、baseline | 更多套件；模型对比；评审定期重新校准 |
| **CI 与代码质量** | 每次提交自动检查 | ruff 做 lint 和格式化；GitHub Actions 跑 pytest（不调用付费 API） | ruff 加 CI | pyright 类型检查；pre-commit |
| **性能与成本** | 缓存友好，用量可控 | 历史只追加；工具集在会话开始时固定；顶层自动缓存；按角色设置 effort | 以上全部 | 并行执行多个工具调用；缓存预热 |
| **Prompt 管理** | 有版本，可以追溯 | prompt 放在文件里，每次请求记录 hash | 文件化和 hash | 改动 prompt 时自动触发 eval 回归 |
| **兼容性** | 能接 DeepSeek 等兼容接口 | `PROFILE` 开关，加上 `diagram` 模板兜底 | PROFILE 开关 | 真机兼容测试；完整的 diagram 模板库 |
| **文档** | 新人能上手，面试时能讲清楚 | README、`decisions.md` 记录每个决策的选择、备选和理由；一页架构图 | README 和 decisions | 完整的架构文档；CHANGELOG |
| **内容质量** | 链接有效，数据格式正确 | `curriculum.yaml` 做 schema 校验；脚本巡检 URL 是否还能打开 | 加载时校验 | 定期巡检；演进清单的季度更新流程 |

---

## 3. 范围划分：主体、扩展、进化

### Phase 1 主体（core，按工程级标准做）

只做“学一篇文章”这个闭环，加上能度量它好不好的 eval：

> 选材 → 抓取、切节 → 概览课件 → 逐节讲解课件 → 助教答疑（隔离） → 总结 → 存进度、续学 → eval 打分

### Phase 2 扩展（设计已定，见附录 B，按价值排序）

1. 面试官加题库（含 C2 收题）；
2. 阅读清单：Chrome 书签同步、`/add`、`+L2`；
3. 术语表和课件悬停解释、`search_learned`；
4. 完整课程 C1：经典论文和 Evals 主线；
5. 备课员、课件设计这两个角色。**只有 eval 或上下文数据显示确实需要时才拆出来**，依据见附录 A.2 那篇“什么时候不该用多 agent”；
6. diagram 模板库；
7. 压缩；
8. DeepSeek 实测和模型对比 eval；
9. `/simpler` 等交互细节。

### Phase 3 进化（设计见附录 B.7）

- 反思员 L1：学习者画像；
- 反思员 L2：skill 进化，在 eval 上训练集迭代、测试集验收，你批准后才合并。

---

## 4. 执行顺序

一次只做一个里程碑。每个做完：
- 我讲解关键设计和代码；
- 你运行确认；
- commit，格式是 `feat: loopback - <topic>`。

| # | 内容 | 跑通标准 |
|---|---|---|
| **P0** | 开工前准备：<br>• 合并写出 `docs/agent-evolution.md`（附录 A）；<br>• `uv self update` 后运行 `uv python install 3.14`；<br>• `docs/plan.md` 换成本计划 | 你审阅新版清单；`uv run python -V` 输出 3.14.8 |
| **M0** | 工程骨架：<br>• src layout、pyproject（3.14，入口是 `loopback`）、uv.lock；<br>• ruff、pytest、CI；<br>• Settings 和 logging；<br>• CLAUDE.md、README、decisions.md | `uv run loopback` 能启动；CI 通过 |
| **M1** | 核心运行时：<br>• `llm`、`session`（事件日志）、`tools`、`loop`、`agents`；<br>• 最小 REPL；<br>• caching 和 `/cost` | 能对话；FakeLLM 测试通过，覆盖 tool 配对、错误路径、中断补齐；第二轮起缓存命中 |
| **M2** | 材料与状态：<br>• `materials`（切节、链接、原图）、`store`（原子写）；<br>• `curriculum.yaml` 初版，内容是官方文档加演进清单；<br>• fetch_material、read_section、progress 三个工具 | Building Effective Agents 生成 sections.json；golden 测试通过 |
| **M3a ✅** | 可用版（2026-10-12 调整，D18、D19）：<br>• 轨迹工具：`/trace` 和 `loopback trace`；<br>• 项目自学分组：用 loopback 学 loopback；<br>• 启动时在本地显示进度，`next` 由 harness 定位下一节；<br>• REPL 从 cli.py 拆出；<br>• 每个函数补上“做什么”的注释 | 用 Claude 冒烟：学 loop.py，从概览到第 1 节，讲解时按行号讲；`/trace` 正常 |
| **M3c ✅** | Claude Code 前端（D20）：<br>• `loopback mcp`：stdio MCP server，暴露同一份学习工具和 `next_step`；<br>• 项目 `.mcp.json`；<br>• `/learn` skill，注入 teacher.md；<br>• 助教用 side chat（`/btw`） | 在 Claude Code 里（Pro 订阅）用 `/learn next` 跑通：next_step → fetch_material → update_progress → 概览 |
| **M3b ✅** | HTML 课件（D21）：<br>• `render_lesson` 支持 8 种块，原文按段号插入；<br>• SVG 消毒；<br>• mermaid 三层防线；<br>• 目录和翻页；<br>• 每节打分存进 `feedback.jsonl`；<br>• skill 设为只读 | Claude Code 冒烟：loop.py 的概览和第 1 节课件一次生成成功；无头 Chrome 截图确认图、分步播放、折叠块都能显示 |
| **M4** | 助教：<br>• `?` 旁支对话、follow_link、`ask`；<br>• 官方接口时带 web_search | 隔离测试通过（确定性检查）；`?L2` 能讲清楚 |
| **M5** | Evals 核心：<br>• runner、graders、judge、report；<br>• teacher 和 ta 两个套件，各约 15 题；<br>• 用你的打分校准评审；<br>• 跑出 baseline | oracle 和 null 基线符合预期；评审和你的一致率 ≥90%；baseline 报告带置信区间 |
| — | **core 完成**，然后按第 3 节进入 Phase 2，再进入 Phase 3；工程化清单里的“后补”项穿插在其中完成 | — |

---

## 5. 验证（core）

- **单元测试**：`uv run pytest` 全部通过，不调用付费 API。
- **端到端**，用 Building Effective Agents 走一遍：
  1. 启动后看到今天的建议；
  2. overview.html 能打开，动画正常；
  3. `next` 生成的课件有原文和中文对照，并且有图；
  4. `?问题` 的内容不在教师的事件日志里；
  5. 学完生成总结；
  6. 重启后能续上进度；
  7. `/cost` 显示缓存读取量大于 0。
- **Eval**：
  - 能跑出 `uv run python -m evals.run --suite teacher --reps 3` 的报告；
  - 总分可以从逐题结果重新算出来，和报告一致；
  - 运行前会先显示预计花费。

---

## 附录 B：已定的设计细节（Phase 2/3 按这些实现）

### B.1 角色（拆分原则：需要隔离上下文、不同权限或不同立场才拆）

| 角色 | 阶段 | 说明 |
|---|---|---|
| 教师 | core | 主会话，负责编排 |
| 助教 | core | 每节一个旁支对话，三类问题，详见 B.2 |
| 面试官 | Phase 2 | 出题、追问、打分（evaluator-optimizer） |
| 备课员 / 课件设计 | Phase 2，有数据支持才拆 | 读全文和画大 SVG 都不进教师的上下文 |
| 反思员 | Phase 3 | 读 transcript，更新画像，提出修改 diff |

- 子 agent 一律拿不到 `ask`，避免无限委派。

### B.2 助教的三类问题

| 类型 | 你怎么问 | 用到的工具 | 结果存到哪 | 阶段 |
|---|---|---|---|---|
| ① 术语 | `?MCP` | `glossary` | `workspace/glossary.json`，课件里鼠标悬停显示 | Phase 2 |
| ② 文中链接详解 | `?L2` | `follow_link`，切节时每节的外链编号成 L1、L2… | — | core |
| ③ 材料之间的关联 | `?和哪篇有关`，或 `+L2` 加进阅读清单 | `search_learned` | — | Phase 2 |

### B.3 大白话规则（写进所有面向你的 prompt）

1. 先给一句不超过 30 字的结论；
2. 用一个生活类比讲透；
3. 新术语第一次出现时写成“中文（English）＋一句话”；
4. 终端里不超过约 8 行，更深的内容放进课件的 `deeper` 折叠块；
5. 能画图就先画图；
6. 不确定就直说。

### B.4 阅读清单和数据归属

- **添加入口**：Chrome 书签文件夹 `loopback` 是主入口，在 `/sync` 时读取 `~/.config/google-chrome/Default/Bookmarks`；另有 `+L2` 和 `/add` 作为补充。
- **公共内容进 git**：代码、`curriculum.yaml`、`interview/bank.yaml`、skills、evals 用例。
- **个人状态放在 `$LOOPBACK_HOME`**（默认 `./workspace`，gitignore 掉）：进度、阅读清单、术语表、反馈、课件、原文、事件日志、作答记录。想备份可以单独建一个私有仓库。

### B.5 面试题库

- **来源**：
  - **A 级**：一手面经，写明公司、岗位、轮次、日期，有原帖链接。已验证牛客帖子能抓到正文和发帖时间。
  - **B 级**：逐题附原帖链接的聚合帖，入库前要回原帖核对措辞。
  - **不收**：没有来源的题目列表和 AI 生成的题库。
- **分档**：
  - **必刷**：同类题在 ≥3 篇一手面经里出现过，或者是核心概念题并有交叉印证；
  - **常见**：出现 1 到 2 次；
  - **拓展**：场景题。
- **evals 方向的必刷题**：怎么评估 agent、LLM-as-judge 的偏差和校准、pass@k 和 pass^k、怎么区分模型问题和 harness 问题、线上反馈怎么变成用例。
- **参考答案的结构**：一句话结论 → 要点（标注出自哪篇哪节）→ 结合 loopback 实现 → 常见追问。题目关联的材料学完后才解锁。
- **样例**：来自牛客 2026-04 的汇总帖，例如腾讯问“多 agent 怎么编排”“上下文超限怎么处理”，百度问“Agent skill 开发怎么做”，字节问“项目架构，每层为什么这么设计”。

### B.6 Evals（照 eval-audit 清单落实）

- **指标按角色拆开**：
  - 教师：忠实度（评审要求引用原句）、覆盖度（代码检查）、大白话规则（代码检查加评审）、图例可用（代码检查）；
  - 助教：忠实度，加上隔离硬门槛；
  - 面试官：和你打分的一致率；
  - 全局：成本、延迟、缓存命中率。
  - 北极星指标是学习效果，只观察，不拿来优化。
- **可信性要求**：
  - 基础设施错误写进 `errors.jsonl`；
  - 每次试验用临时的 `LOOPBACK_HOME` 隔离；
  - 调用真实入口；
  - 每题跑 R 次并报 95% 置信区间，给出噪声底线；
  - oracle 和 null 两条基线；
  - 评审不用被测的模型，随机交换 A/B，防长度偏好，一致率 ≥90%；
  - 核对实际服务的 model；
  - 按 usage 计算成本；
  - 原文快照按 hash 冻结；
  - 运行前确认花费。

### B.7 自我进化

| 层次 | 进化什么 | 怎么进化 | 护栏 |
|---|---|---|---|
| L1 记忆 | 学习者画像 | 每天反思后更新 | 你可以查看、修改、回滚 |
| L2 技能 | skill、范例库、教学 prompt | 失败聚类，提出 diff，训练集上迭代 | 测试集上的提升超过噪声底线、其他指标不退化，并且**你批准**，才合并；记入 `evolution-log` |
| L3 代码和安全规则 | — | 不自动修改，只提建议 | — |

- **反馈信号**：每节打 1 到 5 分、`/bad`，以及隐式信号（`/simpler` 的次数、每节提问数、自测题、面试分）。从 M3 开始采集。

### B.8 课程（C1，Phase 2 完成）

| 级别 | 内容 |
|---|---|
| L0 | Claude Code 和 Codex 官方文档按主题配对，加上 API 基础 |
| L1 | 经典论文：Weng 的综述、CoT、ReAct、Toolformer、Reflexion、Generative Agents、Voyager、MemGPT、SWE-agent |
| L2 | 演进清单的前半部分，加 OpenAI 的 agent 实践指南 |
| L3 | Manus、Cognition、12-Factor、MCP 规范，以及清单的后半部分 |
| L4 | 可靠性与安全 |
| L5 | `openai/codex` 源码、Inspect、agentic RL |
| **Evals 主线（贯穿各级）** | Anthropic 的 7 篇、SWE-bench Verified、τ-bench（pass^k）、METR 时间跨度、MT-Bench 评审偏差、Hamel Husain、Shreya Shankar 等 |

- core 阶段的 `curriculum.yaml` 初版只放官方文档和演进清单。

### B.9 DeepSeek 等纯文本模型

- 图是模型输出的文本，由浏览器渲染，所以纯文本模型照样能出图。
- **手写 SVG 不稳**：用 `diagram` 模板兜底，校验失败就重试一次，再失败就降级。
- **看不懂原图**：原图直接嵌入课件，并标注“未读图”。
- **用不了 Claude 专属功能**：由 PROFILE 关闭。

---

## 附录 A：演进清单的改动明细（2026-10-12，P0 时合并写出 `docs/agent-evolution.md`）

- **核对方法**：对照 anthropic.com 的 sitemap，以及 engineering、news、research 三个栏目和 claude.com/resources/articles，逐篇确认日期。
- **范围**：只覆盖 Anthropic 这一条线。OpenAI、Codex 和经典论文放进 C1。
- **原文件**：`~/Downloads` 里的原文件不动。

### A.1 旧条目修正

| 条目 | 修正 |
|---|---|
| #15 Agent Skills 首次发布 | 补上链接 https://www.anthropic.com/news/skills ，2025-10-16 |
| #23 Equipping agents…Agent Skills | 日期改为 **2025-10-16**（原写 2026.01），移到阶段七 |
| #24 Building agents with the Claude Agent SDK | 日期改为 **2025-09-29**（原写 2026.02），同一天 SDK 改名。链接改为 claude.com/resources/articles/building-agents-with-the-claude-agent-sdk |
| #25 Quantifying infrastructure noise | 日期改为 **2026-02-05**（原写 2026.03） |
| 补漏：Managing context on the Claude Developer Platform（2025-09-29） | context editing 加 memory tool，两者合用比基线高 39%，单独用 context editing 省 84% 的 token |

### A.2 阶段十一　多 agent 实战与长时运行的 harness（2026.01–03）

| 日期 | 文章 | 要点 |
|---|---|---|
| 01-23 | When to use multi-agent systems (and when not to) | 三种情况才用：上下文被污染、任务可并行、工具超过 20 个。token 多花 3 到 10 倍；按上下文边界拆 |
| 02-05 | ⭐ Building a C compiler with a team of parallel Claudes | 16 个 Claude 用 Docker 加 Git 协作，靠任务锁分工。2 周、2000 次会话、2 万美元，写出 10 万行，能编译 Linux 6.9。关键是测试驱动，用 GCC 当参照 |
| 02-18 | ⭐ Measuring AI agent autonomy in practice | 最长自主运行时间从 25 分钟到 45 分钟；老用户 40% 用全自动并且更常中途打断；Claude 主动提问的次数是人打断次数的 2 倍以上 |
| 03-05 | Common workflow patterns for AI agents | 顺序、并行、评估-优化三种模式，可以嵌套，先从单 agent 开始 |
| 03-24 | ⭐ Harness design for long-running application development | 生成器配独立评估器（用 Playwright 实测），迭代 5 到 15 轮，成本 20 倍。主观标准拆成可打分的项。Opus 4.6 不再需要上下文重置 |
| 03-25 | ⭐ How we built Claude Code auto mode | 93% 的权限提示被点了通过；两层防御；分类器两阶段，误杀率从 8.5% 降到 0.4% |

### A.3 阶段十二　把 harness 交给平台托管（2026.04）

| 日期 | 文章 | 要点 |
|---|---|---|
| 04-02 | Agent harness design: 3 patterns | 用通用工具；让代码执行决定哪些结果进上下文；skills 按需加载；缓存友好的排列 |
| 04-08 | ⭐ Scaling Managed Agents: Decoupling the brain from the hands | harness 的假设会随模型变强而过时；推理和沙箱分离；**会话不等于上下文窗口**，会话是只追加的事件日志；一个大脑配多个手 |
| 04-09 | ⭐ Trustworthy agents in practice | 模型、指令、工具、环境四层一起做；用户审批整个计划；防注入靠三道防线 |
| 04-10 | ⭐ Multi-agent coordination patterns | 生成-验证、编排-子 agent、消息总线、共享状态等五种模式，从生成-验证起步 |
| 04-23 | An update on recent Claude Code quality reports（事故复盘） | 推理档降级、缓存 bug 每轮清掉 thinking、新加的字数限制，三层叠加导致质量下降。harness 跨层改动必须整体回归 |
| 04-23 | Memory for Claude Managed Agents | 记忆就是文件，可以限定作用域、可以审计、能并发读写；Rakuten 的错误率降了 97% |

### A.4 阶段十三　自我改进、纵深安全与协议升级（2026.05–07）

| 日期 | 文章 | 要点 |
|---|---|---|
| 05-19 | ⭐ New in Managed Agents: dreaming, outcomes, multiagent orchestration | **dreaming**：回看过去的会话来自我改进，Harvey 的完成率提升约 6 倍；**outcomes**：独立评分器检验，迭代到达标；**多 agent 编排**：子 agent 共享文件系统 |
| 05-25 | ⭐ How we contain Claude across products | 环境隔离优先；沙箱加 auto mode 让权限提示减少 84%；项目配置要等用户同意后才解析；出站流量只放行本会话的令牌 |
| 06-10 | ⭐ The evolution of agentic surfaces | 演进三步：纯 API → 用 Agent SDK 自己管 harness → Managed Agents 全托管；首 token 延迟降低约 60%；用 Vault 隔离凭证 |
| 06-18 | Steering Claude Code: CLAUDE.md, skills, hooks, subagents | 四种机制各自什么时候用；适合在 L0 配合官方文档读 |
| 07-28 | ⭐ MCP 2026-07-28 spec: stateless core | 改成无状态的请求/响应，可以部署到 serverless；Apps 和 Tasks 变成扩展；认证对齐 OAuth / OIDC |

### A.5 阶段十四　多 agent 的风险与长上下文经济学（2026.08–10）

| 日期 | 文章 | 要点 |
|---|---|---|
| 08-13 | ⭐ Patterns and problems in multiagent systems | 30 个 agent 里 18 个建了同名分支；一个任务队列 240 万次请求只接下 117 个任务；小组讨论准确率 17% 到 36%，单独判断是 100%；目标冲突会升级成对抗 |
| 09-24 | Coding sessions use more context: Opus 5.5 | 单次请求的上下文增长 2.6 倍；输入输出比从 189:1 到 324:1；缓存价格降了 60% |
| 10-09 | ⭐ Investigating unintended model actions | 4 类越界行为；应对是自动检测、收紧联网、集中管理基础设施 |

### A.6 里程碑速查

- **模型**：
  - Opus 4.5（2025-11-24）
  - Opus 4.6（2026-02-05）
  - Sonnet 4.6（02-17）
  - Mythos Preview（04-07）
  - Opus 4.7（04-16）
  - Opus 4.8（05-28）
  - Fable 5 / Mythos 5（06-09）
  - Sonnet 5（06-30）
  - Opus 5（07-24）
  - Opus 5.5（09-22）
- **Claude Code**：
  - routines（04-14）
  - 桌面版为并行 agent 重新设计（04-14）
  - agent view（05-11）
  - dynamic workflows（05-28）
  - artifacts（06-18）
  - 自托管环境（08-06）
  - auto mode 成为默认（08-07）
  - TypeScript mods（10-01）
- **平台**：
  - Managed Agents（04-08）
  - Claude Tag（06-23）
  - Claude in Chrome 正式发布（08-26）
  - Cowork 与聊天合并（09-16）

### A.7 演进主线（新增五步）

1. 多 agent 实战与自主权限；
2. 托管化：会话不等于上下文窗口；
3. 自我改进：memory、dreaming、outcomes；
4. 纵深安全：containment；
5. 协议无状态化与上下文经济学。
