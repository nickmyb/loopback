# loopback：自学 Claude Code / Codex 的多 agent 终端学习系统

> 定稿：2026-10-12。2026-10-13 按 D25 分层：需求移到 `docs/requirements.md`，架构移到 `docs/architecture.md`，工作方式只写在 `CLAUDE.md`。
>
> 这份文档只管三件事：范围、里程碑和状态，以及 Phase 2/3 已经定下的设计（附录 B）。计划有变动时直接改这里，并在 `docs/decisions.md` 里记下原因。

## Context

**目标**：做一个**工程级**（不是 demo）的终端学习 agent。它带着学习者从零学到能拿下 agent 研发岗位，开发它的过程本身就是一次完整的 agent 工程实践。

**节奏**：**先把主体（core）做扎实**。主体之外的细节和体力活，先写清楚“在哪里补、补什么、怎么补”，等 core 完成后再做。

**需求**：R1–R16 见 `docs/requirements.md`。那里是唯一来源，编号只追加。

---

## 1. 架构

已移到 `docs/architecture.md`。那里描述代码现在的样子，并随代码一起更新。这里保留标题，是为了不打乱后面各节的编号。

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
| **测试** | 不花钱就能验证核心逻辑 | 用 `FakeLLM` 按剧本测：tool 配对、错误路径、助教隔离、恢复；切页用 golden 文件测；渲染用快照测 | 核心路径的测试 | 覆盖率补到 80% 以上；属性测试 |
| **Evals** | 效果可度量、可信，详见附录 B.6 | runner 支持多次重复加置信区间；基础设施错误单独记录；oracle 和 null 两条基线；评审先用人工标注校准；报告带完整轨迹 | runner、评分器、teacher 和 ta 两个小套件、baseline | 更多套件；模型对比；评审定期重新校准 |
| **CI 与代码质量** | 每次提交自动检查 | ruff 做 lint 和格式化；GitHub Actions 跑 pytest（不调用付费 API） | ruff 加 CI | pyright 类型检查；pre-commit |
| **性能与成本** | 缓存友好，用量可控 | 历史只追加；工具集在会话开始时固定；顶层自动缓存；按角色设置 effort | 以上全部 | 并行执行多个工具调用；缓存预热 |
| **Prompt 管理** | 有版本，可以追溯 | prompt 放在文件里，每次请求记录 hash | 文件化和 hash | 改动 prompt 时自动触发 eval 回归 |
| **兼容性** | 能接 DeepSeek 等兼容接口 | `PROFILE` 开关，加上 `diagram` 模板兜底 | PROFILE 开关 | 真机兼容测试；完整的 diagram 模板库 |
| **文档** | 新人能上手，面试时能讲清楚；同一内容只写一份 | README；`requirements.md` 记需求和验收方式；`architecture.md` 记现状；`decisions.md` 记每个决策的选择、备选和理由；`tests/test_docs.py` 做文档自检（D25） | 以上全部（M6a） | CHANGELOG |
| **内容质量** | 链接有效，数据格式正确 | `curriculum.yaml` 做 schema 校验；脚本巡检 URL 是否还能打开 | 加载时校验 | 定期巡检；演进清单的季度更新流程 |

---

## 3. 范围划分：主体、扩展、进化

### Phase 1 主体（core，按工程级标准做）

只做“学一篇文章”这个闭环，加上能度量它好不好的 eval：

> 选材 → 抓取、切页 → 概览课件 → 逐页讲解课件 → 助教答疑（隔离） → 总结 → 存进度、续学 → eval 打分

### Phase 2 扩展（设计已定，见附录 B，按价值排序）

1. 面试官加题库（含 C2 收题）；
2. 阅读清单：Chrome 书签同步、`/add`、`+L2`（存储已在 M3d 提前做好：`curriculum.local.yaml`，目前只能手写）；
3. 术语表和课件悬停解释、`search_learned`；
4. 完整课程 C1：经典论文和 Evals 主线；
5. 备课员、课件设计这两个角色。**只有 eval 或上下文数据显示确实需要时才拆出来**，依据见演进清单里《When to use multi-agent systems (and when not to)》那篇；
6. diagram 模板库；
7. 压缩；
8. DeepSeek 实测和模型对比 eval；
9. `/simpler` 等交互细节。

### Phase 3 进化（设计见附录 B.7）

- 反思员 L1：学习者画像；
- 反思员 L2：skill 进化，在 eval 上训练集迭代、测试集验收，你批准后才合并。

---

## 4. 执行顺序

一次只做一个里程碑。做法和四个确认点见 `CLAUDE.md` 的「工作方式」。每个里程碑的蓝图和验收记录放在 `docs/milestones/` 下。

状态用五个标记：
- ✅ 完成，后面附提交号；
- 🟡 部分完成；
- 🔄 进行中；
- ⏸ 延后；
- ⬜ 未开始。

表格按实际执行的顺序排列。编号只追加，不重排（D25）。

| # | 状态 | 内容 | 跑通标准 |
|---|---|---|---|
| **P0** | ✅ e56758b | 开工前准备：<br>• 合并写出 `docs/agent-evolution.md`，改动明细见 `docs/milestones/P0.md`；<br>• `uv self update` 后运行 `uv python install 3.14`；<br>• `docs/plan.md` 换成本计划 | 你审阅新版清单；`uv run python -V` 输出 3.14.8 |
| **M0** | ✅ 9d8b6c1 | 工程骨架：<br>• src layout、pyproject（3.14，入口是 `loopback`）、uv.lock；<br>• ruff、pytest、CI；<br>• Settings 和 logging；<br>• CLAUDE.md、README、decisions.md | `uv run loopback` 能启动；CI 通过 |
| **M1** | ✅ 1d068a5 | 核心运行时：<br>• `llm`、`session`（事件日志）、`tools`、`loop`、`agents`；<br>• 最小 REPL；<br>• caching 和 `/cost` | 能对话；FakeLLM 测试通过，覆盖 tool 配对、错误路径、中断补齐；第二轮起缓存命中 |
| **M2** | ✅ cb22a67 | 材料与状态：<br>• `materials`（切节、链接、原图）、`store`（原子写）；<br>• `curriculum.yaml` 初版，内容是官方文档加演进清单；<br>• fetch_material、read_section、progress 三个工具 | Building Effective Agents 生成 sections.json；golden 测试通过 |
| **M3a** | ✅ f063dd5 | 可用版（2026-10-12 调整，D18、D19）：<br>• 轨迹工具：`/trace` 和 `loopback trace`；<br>• 项目自学分组：用 loopback 学 loopback；<br>• 启动时在本地显示进度，`next` 由 harness 定位下一节；<br>• REPL 从 cli.py 拆出；<br>• 每个函数补上“做什么”的注释 | 用 Claude 冒烟：学 loop.py，从概览到第 1 节，讲解时按行号讲；`/trace` 正常 |
| **M3c** | ✅ 6d837a5 | Claude Code 前端（D20）：<br>• `loopback mcp`：stdio MCP server，暴露同一份学习工具和 `next_step`；<br>• 项目 `.mcp.json`；<br>• `/learn` skill，注入 teacher.md；<br>• 助教用 side chat（`/btw`） | 在 Claude Code 里（Pro 订阅）用 `/learn next` 跑通：next_step → fetch_material → update_progress → 概览 |
| **M3b** | ✅ c922960 | HTML 课件（D21）：<br>• `render_lesson` 支持 8 种块，原文按段号插入；<br>• SVG 消毒；<br>• mermaid 三层防线；<br>• 目录和翻页；<br>• 每节打分存进 `feedback.jsonl`；<br>• skill 设为只读（后来发现只管一轮，见 D27） | Claude Code 冒烟：loop.py 的概览和第 1 节课件一次生成成功；无头 Chrome 截图确认图、分步播放、折叠块都能显示 |
| **M5** | 🟡 570f94e | Evals 核心（D22）：<br>• `evals/` 包含 runner、graders、judge、stats、report、calibrate；<br>• teacher 套件 11 个用例（section、start、finish）；<br>• oracle 和 null 基线 | ✅ oracle 11/11、null 0/11；92 个单元测试通过<br>⏳ 付费 baseline（花费确认后再跑）<br>⏳ 评审校准（需要你标注约 30 条，一致率 ≥90%） |
| **M3d** | ✅ 703644c | 个人课程（2026-10-13 插入，D23）：<br>• `$LOOPBACK_HOME/curriculum.local.yaml` 追加在公共课程后面，校验规则相同；<br>• 手写错误给出带文件名的说明；<br>• 这是阅读清单（Phase 2 第 2 项）的最小版 | 98 个单元测试通过；把 go.dev/blog/pipelines 加进个人课程后，`/mcp` 重连，`/learn go-pipelines` 能学 |
| **M6a** | ✅ 0c94d1e | 复盘修复：文档分层（D25、D26，蓝图见 `docs/milestones/M6.md`）：<br>• CLAUDE.md 只放规则、工作方式和文档地图；<br>• 新增 requirements.md、architecture.md、`docs/milestones/`；<br>• `.claude/rules/` 放按路径加载的规则；<br>• 补记 D24–D27；<br>• 文档自检测试 | `tests/test_docs.py` 通过：模块表和实际文件一致、每个里程碑都有状态、编号连续、确认点叫法统一 |
| **M6b** | ✅ 0f4fddd | 复盘修复：课件和切节：<br>• 原文里的代码块、ASCII 图和表格不折行，含有它们的段落改成上下排；<br>• 全篇结构图不用 mindmap，渲染后检测节点重叠；<br>• loopback 的单位改叫“页”，提到内容位置时写原文标题；<br>• 切节时去掉分隔线，表格和它的引导句不拆开；<br>• 开始学一篇时冻结材料快照，页号不随原文变化 | 架构图、目录树、工程化清单三处改前改后的截图对比；repo-plan 没有只含分隔线的页；学习途中改原文不影响页号 |
| **M6c** | ✅ | 复盘修复：运行时：<br>• AgentSpec 可以按角色配置模型；<br>• 反馈分页和篇两级，回 `next 4` 就是打 4 分并继续，两个前端都主动问 | FakeLLM 测试覆盖按角色配置模型；两个前端各学一页，都能记下页级评分 |
| **M6d** | ⬜ | 复盘修复：Claude Code 角色入口（D27）：<br>• `.claude/agents/` 里写教师和助教的定义，工具只读；<br>• `loopback study` 打开 agent view；<br>• `/learn` 用 hooks 兜底；<br>• settings 里用 deny 规则挡住 `.env` | 连续两轮实测，Edit 和 Write 都不可用；`@loopback-ta` 能查仓库和官方文档 |
| **M6e** | ⬜ | 复盘修复：日志和助教问题：<br>• `loopback import-cc` 把 Claude Code 的对话日志转成事件日志：按响应去重、合并 `/btw` 的问题、算出隐式信号；<br>• 附录 B.2 按 17 条真实问题改写；<br>• 这 17 条问题作为助教 eval 的第一批用例 | 导入学习会话后能用 `loopback trace` 查看；调用次数和用量与 Claude Code 的记录一致（104 次调用） |
| **M4** | ⬜ | 助教（D24：之前延后，现在按真实提问重新设计）：<br>• REPL 里用 `?` 开旁支会话，只给只读工具：follow_link、查仓库，官方接口时加 web_search；<br>• `teacher_context` 读学习会话当前的位置；<br>• 问题记进 `questions.jsonl`；<br>• 委派工具 `ask` | 隔离测试通过（确定性检查）；助教 eval 的首批用例能跑；`?L2` 能讲清楚 |
| — | — | **core 完成**，然后按「范围划分」进入 Phase 2，再进入 Phase 3；工程化清单里的“后补”项穿插在其中完成 | — |

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
| 助教 | core | 每页一个旁支对话，三类问题，详见 B.2 |
| 面试官 | Phase 2 | 出题、追问、打分（evaluator-optimizer） |
| 备课员 / 课件设计 | Phase 2，有数据支持才拆 | 读全文和画大 SVG 都不进教师的上下文 |
| 反思员 | Phase 3 | 读 transcript，更新画像，提出修改 diff |

- `ask` 是 M4 计划中的委派工具：教师或助教调用它时，会起一个上下文全新、只有只读工具的子 agent 去查，只把最终答案交回来。子 agent 一律拿不到 `ask`，所以委派最多一层，不会无限递归。它和 Claude Code 里向你提选择题的 `AskUserQuestion` 不是一回事。
- **在 Claude Code 里怎么落地**（D27）：直接跟你对话的角色（教师、助教，以后的面试官）各是 `.claude/agents/` 里的一份定义，从 agent view 用 `@名字` 启动；不跟你对话的角色（备课员、课件设计、委派）是子 agent，由教师调用；反思员由命令批量运行。

### B.2 助教的三类问题

> 2026-10-13：学完两篇项目文档后，按 17 条真实的 `/btw` 提问重新归纳了问题类型，这张表在 M6e 更新（D24）。

| 类型 | 你怎么问 | 用到的工具 | 结果存到哪 | 阶段 |
|---|---|---|---|---|
| ① 术语 | `?MCP` | `glossary` | `workspace/glossary.json`，课件里鼠标悬停显示 | Phase 2 |
| ② 文中链接详解 | `?L2` | `follow_link`，切页时每页的外链编号成 L1、L2… | — | core |
| ③ 材料之间的关联 | `?和哪篇有关`，或 `+L2` 加进阅读清单 | `search_learned` | — | Phase 2 |

### B.3 大白话规则（写进所有面向你的 prompt）

1. 先给一句不超过 30 字的结论；
2. 用一个生活类比讲透；
3. 新术语第一次出现时写成“中文（English）＋一句话”；
4. 终端里不超过约 8 行，更深的内容放进课件的 `deeper` 折叠块；
5. 能画图就先画图；
6. 不确定就直说。

### B.4 阅读清单和数据归属

- **添加入口**：Chrome 书签文件夹 `loopback` 是主入口，在 `/sync` 时读取 `~/.config/google-chrome/Default/Bookmarks`；另有 `+L2` 和 `/add` 作为补充。这些入口都写进 `$LOOPBACK_HOME/curriculum.local.yaml`（D23）。
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

- **反馈信号**：每页打 1 到 5 分、`/bad`，以及隐式信号（`/simpler` 的次数、每页提问数、自测题、面试分）。从 M3 开始采集。不过 Claude Code 前端实际上几乎没采集到：M6c 改成每页、每篇两级评分，M6e 从对话日志里算出隐式信号。

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

## 附录 A：演进清单的改动明细

已移到 `docs/milestones/P0.md`。那是 P0 当时的记录，冻结不改。
