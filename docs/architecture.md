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

 every agent = AgentSpec(prompt file, tool set, effort), run by the SAME agent_loop
 agent_loop(session, spec, llm):
     stream request -> append assistant event -> run tools -> append tool_results event -> repeat
 session = append-only event log (JSONL) --projection--> messages sent to the API
 state   = files under $LOOPBACK_HOME (progress, library, lessons, feedback, sessions, evals, logs)
```

- 不同的角色只是 AgentSpec 不同（D2）。目前实际运行的只有教师这一个角色。按角色配置模型在 M6c 加上。
- 学习能力（课程、材料库、进度、课件、反馈）和前端无关，两个前端用的是同一套工具（D20）。
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
| `src/loopback/config.py` | 从环境变量读出只读的 Settings 和能力档案 Profile；配置日志 |
| `src/loopback/llm.py` | `LLM` protocol、Anthropic 的流式实现、请求构造（缓存和 effort 由 Profile 决定） |
| `src/loopback/session.py` | 只追加的事件日志，以及把它投影成 messages 的规则 |
| `src/loopback/tools.py` | 工具注册表：校验输入、执行，把异常包成带 `is_error` 的结果 |
| `src/loopback/loop.py` | agent_loop：所有角色共用的循环，保证每个 tool_use 都有 tool_result |
| `src/loopback/agents.py` | AgentSpec：prompt 文件、工具集、运行参数和 prompt hash |
| `src/loopback/store.py` | 状态文件的原子写，以及 version 字段 |
| `src/loopback/extract.py` | 把网页转成 markdown 正文（D16） |
| `src/loopback/materials.py` | 把 markdown 切成节：标题路径、链接编号 L#、图片编号 I#、段号 P# |
| `src/loopback/library.py` | 材料库：抓取、切节、缓存，提供大纲和单节读取 |
| `src/loopback/repo.py` | 项目自学：把本仓库的文件当材料，源码按函数和类切节（D19） |
| `src/loopback/curriculum.py` | 课程表（公共课程加个人课程，D23）和学习进度 |
| `src/loopback/learning.py` | 教师用的学习工具：find_material、curriculum_status、fetch_material、read_section、update_progress |
| `src/loopback/render.py` | 课件的整页：模板、翻页、目录页，以及 render_lesson 工具（D21） |
| `src/loopback/blocks.py` | 课件的内容块：校验后转成安全的 HTML；mermaid lint |
| `src/loopback/svg.py` | SVG 消毒 |
| `src/loopback/feedback.py` | 记录学习者的打分，写进 feedback.jsonl |
| `src/loopback/files.py` | 只能访问 $LOOPBACK_HOME 的文件工具；目前没有角色在用（D17） |
| `src/loopback/pricing.py` | 按 usage 估算花费和缓存命中率 |
| `src/loopback/trace.py` | 轨迹：把事件日志整理成“轮 → 模型调用 → 工具调用”（D18） |
| `src/loopback/repl.py` | 终端 REPL：分发输入、处理 `/` 命令、问学习者打分 |
| `src/loopback/cli.py` | 命令行入口：REPL，以及 `trace`、`mcp` 两个子命令 |
| `src/loopback/mcp_server.py` | Claude Code 前端：把学习工具做成 stdio MCP server（D20） |
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

## 学一节的数据流

```
next -> next_step / curriculum_status      where am I? (progress.json)
     -> fetch_material(id)                 library: fetch -> extract -> split -> cache; returns the outline
     -> read_section(id, n)                one section, wrapped in <material> (untrusted text)
     -> explain in the terminal + render_lesson(blocks)
                                           render / blocks / svg -> lessons/<id>/sNN.html, open the browser
     -> update_progress(id, n)             progress.json (atomic write)
     -> record_feedback(...)               feedback.jsonl
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
| `library/<id>/` | 抓来的原文和切好的节。项目自学的条目不缓存，每次实时读取 |
| `lessons/<id>/` | HTML 课件和目录页 |
| `feedback.jsonl` | 打分 |
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
| 助教 | 计划中（M4） | 暂时用 `/btw`，查不了资料。M6d 改成单独的助教会话（D24、D27） |
