# 架构（现状）

这份文档描述代码现在的样子，随代码一起更新（D25）。需求见 `requirements.md`，计划和进度见 `plan.md`，每个设计为什么这样选见 `decisions.md`。

## 技术选型

- Python 3.14.8，由 uv 管理解释器和依赖。采用 src layout，入口是 `uv run loopback`（D12）。
- 直接用官方的 `anthropic` SDK，不用 agent 框架（D12）。
- 配置来自环境变量和 `.env`：`ANTHROPIC_API_KEY`、`MODEL_ID`、`ANTHROPIC_BASE_URL`。默认模型是 `claude-opus-5-5`。
- 接 DeepSeek 这类兼容接口时，用能力档案 Profile 关掉 Claude 专属的能力（D7）。

## 总体结构

```
 learner
   |
   +-- REPL: uv run loopback (API) ---+-- next / free text --> TEACHER (AgentSpec, own session)
   |                                  +-- ?question ---------> TA (planned, M4)
   |                                  +-- /commands ---------> harness code (progress, trace, cost)
   |
   +-- Claude Code: /learn (subscription) -- MCP stdio --> loopback mcp --> same learning tools + next_step
         (loop, model and transcript belong to Claude Code)

 every agent = AgentSpec(prompt file, tool set, model, effort), run by the SAME agent_loop
 agent_loop(session, spec, llm):
     stream request -> append assistant event -> run tools -> append tool_results event -> repeat
 session = append-only event log (JSONL) --projection--> messages sent to the API
 state   = files under $LOOPBACK_HOME (progress, library, lessons, feedback, sessions, evals, logs)
```

- 不同的角色只是 AgentSpec 不同（D2）。目前实际运行的只有教师这一个角色；每个角色可以单独配置模型（D31）。
- 学习能力（课程、材料库、进度、课件、反馈）和前端无关，两个前端用的是同一套工具（D20）。
- 代码里的 section 就是中文说的“页”：loopback 把一篇材料切成一页一页，“节”只用来说原文自己的结构（D29）。
- 三个事后很难再改的底层决策，在 core 阶段就定了下来：
  1. 会话是只追加的事件日志，messages 只是它的投影（D3）；
  2. LLM 通过接口注入，测试时用 FakeLLM（D4）；
  3. prompt 放在文件里，每次请求都记下它的 hash（D5）。

## 模块

`tests/test_docs.py` 会检查这张表和实际文件是否一致：
- 表里列的文件必须存在；标了“未实现”的反过来，必须不存在；
- `src/loopback/` 和 `evals/` 下的每个 `.py` 文件都必须出现在表里。

| 文件 | 做什么 |
|---|---|
| `src/loopback/config.py` | 从环境变量读出只读的 Settings、能力档案 Profile 和按角色的模型（D31）；配置日志 |
| `src/loopback/llm.py` | `LLM` protocol、Anthropic 的流式实现、请求构造（缓存和 effort 由 Profile 决定） |
| `src/loopback/session.py` | 只追加的事件日志，以及把它投影成 messages 的规则 |
| `src/loopback/tools.py` | 工具注册表：校验输入、执行，把异常包成带 `is_error` 的结果 |
| `src/loopback/loop.py` | agent_loop：所有角色共用的循环，保证每个 tool_use 都有 tool_result |
| `src/loopback/agents.py` | AgentSpec：prompt 文件、工具集、运行参数和 prompt hash |
| `src/loopback/store.py` | 状态文件的原子写，以及 version 字段 |
| `src/loopback/extract.py` | 把网页转成 markdown 正文（D16） |
| `src/loopback/materials.py` | 把 markdown 切成页：表格和代码块不拆、去掉分隔线、短尾巴合并；标题路径、链接编号 L#、图片编号 I#、段号 P# |
| `src/loopback/fetch.py` | 抓网页：重试、超时，把网络错误转成给模型看的报错 |
| `src/loopback/library.py` | 材料库：每篇材料第一次读取时切好页，冻结成快照；需要时按最新原文重建（D28） |
| `src/loopback/reading.py` | 按需读取：给教师看的大纲和单页原文（包在 `<material>` 里） |
| `src/loopback/repo.py` | 项目自学：把本仓库的文件当材料，源码按函数和类切页（D19）；和网页材料一样有快照（D28） |
| `src/loopback/curriculum.py` | 课程表：公共课程加个人课程（D23），加载时校验，按标题搜索 |
| `src/loopback/progress.py` | 学习进度：学到哪了、下一步做什么（`next` 由代码算出） |
| `src/loopback/learning.py` | 教师用的学习工具：find_material、curriculum_status、fetch_material、read_section、update_progress |
| `src/loopback/render.py` | 课件的整页：模板、翻页、目录页，以及 render_lesson 工具（D21） |
| `src/loopback/blocks.py` | 课件的内容块：校验后转成安全的 HTML；mermaid lint |
| `src/loopback/svg.py` | SVG 消毒 |
| `src/loopback/feedback.py` | 反馈的记录格式：每页、每篇的分数，带页标题、快照时间、前端、prompt 版本（D32）；`record_feedback` 工具 |
| `src/loopback/rating.py` | 打分的入口：解析 `next 4`、`/rate 4`；`Rater` 记下刚学完的那一页或那一篇（两个前端共用） |
| `src/loopback/files.py` | 只能访问 $LOOPBACK_HOME 的文件工具；目前没有角色在用（D17） |
| `src/loopback/pricing.py` | 按 usage 估算花费和缓存命中率 |
| `src/loopback/trace.py` | 轨迹：把事件日志整理成“轮 → 模型调用 → 工具调用”（D18） |
| `src/loopback/repl.py` | 终端 REPL：主循环和命令分发（`handle`），`next` 的流程 |
| `src/loopback/display.py` | 终端里的显示：工具调用提示、一轮结束时的说明、用量和花费、接口错误 |
| `src/loopback/cli.py` | 命令行入口：REPL，以及 `trace`、`mcp` 两个子命令 |
| `src/loopback/mcp_server.py` | Claude Code 前端：把学习工具做成 stdio MCP server（D20），外加只有它用的 `next_step`（可以顺带给刚学完的页打分，D32） |
| `src/loopback/__init__.py` | 包说明 |
| `src/loopback/prompts/teacher.md` | 教师 prompt，两个前端共用这一份 |
| `src/loopback/templates/lesson.html` | 课件模板：配色、深色模式、mermaid 出错时的降级显示、分步播放 |
| `src/loopback/data/curriculum.yaml` | 公共课程表 |
| `src/loopback/skills.py` | 未实现。两层 SkillLoader：D21 决定暂不做；等 Phase 3 技能进化需要按 skill 管理版本时再做 |
| `src/loopback/prompts/ta.md` | 未实现。助教的 prompt（M4） |
| `evals/run.py` | eval 命令行：冻结材料、确认花费、逐个试验、汇总报告 |
| `evals/harness.py` | 跑一次试验：独立的临时 LOOPBACK_HOME，走真实入口 |
| `evals/cases.py` | 加载并校验用例集 `evals/suites/*.yaml` |
| `evals/graders.py` | 代码评分：从轨迹和产物里做确定性的检查 |
| `evals/judge.py` | LLM 评审：逐段判断是否忠实于原文，检查大白话规则 |
| `evals/scoring.py` | 单次试验的评分、评审和记账 |
| `evals/scripted.py` | 剧本 LLM：提供 oracle 和 null 两条基线 |
| `evals/stats.py` | 均值、95% 置信区间、噪声底线 |
| `evals/budget.py` | 开跑前估算花费并请用户确认 |
| `evals/report.py` | 生成 summary.json 和 report.html |
| `evals/calibrate.py` | 评审校准：计算评审和人工标注的一致率 |
| `evals/__init__.py` | 包说明 |
| `.mcp.json` | 登记 loopback 的 MCP server |
| `.claude/skills/learn/SKILL.md` | Claude Code 的 `/learn`：注入教师 prompt |
| `.github/workflows/ci.yml` | CI：跑 ruff 和 pytest，不调用付费 API |

## 学一页的数据流

```
next -> next_step / curriculum_status      where am I? (progress.json)
     -> fetch_material(id)                 library snapshot: fetch -> extract -> split on first use,
                                           re-split when (re)starting the item; returns the outline
     -> read_section(id, n)                one page from the snapshot, wrapped in <material> (untrusted)
     -> explain in the terminal + render_lesson(blocks)
                                           render / blocks / svg -> lessons/<id>/sNN.html, open the browser
     -> update_progress(id, n)             progress.json (atomic write)
     -> next 4 / /rate 4 / record_feedback  feedback.jsonl (page or article rating, D32)
```

## 事件日志

REPL 的每个会话是 `$LOOPBACK_HOME/sessions/<会话>.jsonl`，每行一个事件，只追加（D3）。

| 事件 | 内容 | 是否进入投影 |
|---|---|---|
| `user` | 学习者的一次输入 | 是，role 为 user |
| `assistant` | 模型的完整回复（包括 thinking 和 tool_use），另记 agent、实际服务的 model、stop_reason、usage、request_id、耗时、prompt_hash | 是 |
| `tool_results` | 这条回复里每个 tool_use 的结果，一次写齐 | 是，role 为 user，排在消息最前面 |
| `turn_failed` | 请求失败（API 错误或 Ctrl-C）。如果某条输入在失败前一次回答都没得到，就把它从投影里撤回（D15） | 否 |

投影时有两条规则：相邻的、角色相同的事件合并成一条消息；`tool_result` 块排在 user 消息的最前面。

## 个人状态

个人状态都放在 `$LOOPBACK_HOME` 里，默认是 `workspace/`，不进 git（D6）。

| 路径 | 内容 |
|---|---|
| `progress.json` | 学习进度 |
| `curriculum.local.yaml` | 个人课程，手写（D23） |
| `library/<id>/` | 网页原文 `source.md`，以及快照 `sections.json`：切好的页，外加 `source_hash`、`split_version`、`snapshot_at`。项目文件也有快照（D28） |
| `lessons/<id>/` | HTML 课件和目录页 |
| `feedback.jsonl` | 打分：每页、每篇各一个分，带页标题、快照时间、前端、prompt 版本（D32） |
| `sessions/` | REPL 的事件日志 |
| `logs/` | 运行日志 |
| `evals/cache/`、`evals/runs/` | eval 的材料快照，以及每次运行的结果 |

## 两个前端的差别

| | REPL（`uv run loopback`） | Claude Code（`/learn`） |
|---|---|---|
| agent loop | loopback 自己的 | Claude Code 的 |
| 模型和费用 | 走 API，按 usage 计费 | 走订阅额度 |
| 工具 | 只有 loopback 的学习工具 | 同一套学习工具，通过 MCP 接入；另外还有 Claude Code 自带的工具 |
| 学习时只读 | 天然只读：教师没有写文件的工具 | 目前没有保证：第一轮之后 Edit 和 Write 又能用了（D27，M6d 修） |
| 事件日志和 `/trace` | 有 | 没有。对话记录在 `~/.claude/projects/` 下，M6e 做导入 |
| 打分 | `next 4`、`/rate 4`，harness 直接记 | 回 `next 4` 时教师调用 `next_step(rating=4)`；整篇由教师调用 `record_feedback` |
| 助教 | 计划中（M4） | 暂时用 `/btw`，查不了资料。M6d 改成单独的助教会话（D24、D27） |
