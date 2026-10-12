# 设计决策记录

每条记录写清四件事：**决策**是什么、考虑过哪些**备选**、**理由**，以及面试被追问“为什么这么设计”时可以怎么讲。新决策追加在文末，编号不复用。

---

## D1 终端对话 + HTML 课件

- **决策**：学习对话在终端里进行；概览、逐节讲解、总结做成独立的 HTML 文件，自动在浏览器里打开。
- **备选**：本地 Web 应用（左边聊天、右边课件）；纯终端加 ASCII 图。
- **理由**：
  - agent 开发正在以终端为主。
  - HTML 用 SVG、CSS 动画和 mermaid 画图最简单，中文排版也不会错位。
  - Web 应用的前后端代码会把 agent 的核心淹没。
- **面试怎么讲**：交互面和呈现面分离；呈现是确定性代码，模型只出内容。

## D2 只有一个 agent_loop，角色就是配置

- **决策**：教师、助教、子 agent 等所有角色都由同一个 `agent_loop` 驱动。角色本身只是一份 `AgentSpec`，包含 prompt 文件、工具集、模型和 effort。
- **备选**：每个角色单独写一套代码；用 LangChain 之类的框架。
- **理由**：subagent 本质上就是一个新的 messages 列表（learn-claude-code s04）。一份循环、多份配置，测试和 eval 都只需覆盖一处。
- **面试怎么讲**：“agent = 循环 + prompt + 工具”，把多 agent 的复杂度压到配置层。

## D3 会话 = 只追加的事件日志，messages 是投影

- **决策**：会话的唯一事实来源是 JSONL 事件日志，只追加不修改。发给 API 的 messages 由事件日志投影得到。
- **备选**：直接在内存里维护 messages 列表并原地修改，例如 learn-claude-code s06 的 micro_compact。
- **理由**：
  - Opus 5.5 有 preserved thinking：改写历史会让 thinking block 失效，新账号会直接报 400；同时 prompt 缓存要求前缀不变。
  - 事件日志可以在中断后恢复，eval 和反思员也能直接读取。
  - 压缩时只需换一种投影方式，比如“摘要 + 最近几轮”。
  - 思路来自 Anthropic《Scaling Managed Agents》：会话不等于上下文窗口。
- **面试怎么讲**：event sourcing 用在 agent 上；上下文窗口只是会话的一个视图。

## D4 LLM 通过接口注入

- **决策**：`agent_loop` 依赖一个 `LLM` protocol。生产环境用 Anthropic client，测试时用 `FakeLLM` 按剧本返回预设响应。
- **备选**：直接在 loop 里调用 SDK，靠 mock 打补丁来测试。
- **理由**：tool 配对、错误路径、上下文隔离、恢复这些核心逻辑，都能在不花钱、确定性的单元测试里验证。
- **面试怎么讲**：harness 逻辑和模型能力分开测。单元测试测 harness，eval 测模型加 harness 的整体效果。

## D5 prompt 和 skill 放在文件里，每次请求记录 hash

- **决策**：system prompt 和 SKILL.md 都是仓库里的文件。每次请求在事件日志里记下它们的 hash。
- **备选**：prompt 写成代码里的字符串。
- **理由**：eval 结果和进化记录必须能对应到具体的 prompt 版本；prompt 的 diff 也要能走 code review。
- **面试怎么讲**：prompt 也是代码，要有版本，要能回归。

## D6 公共内容和个人状态分开存放

- **决策**：
  - 代码、课程表、题库、skills、eval 用例进 git。
  - 进度、阅读清单、术语表、课件、抓来的原文、事件日志放在 `$LOOPBACK_HOME`，默认是 `workspace/`，不进 git。
- **备选**：所有东西都进 git。
- **理由**：阅读状态因人而异；原文有版权；别人 clone 后应该从空状态开始。想备份的话，可以把 workspace 单独建成一个私有仓库。
- **面试怎么讲**：明确数据归属，区分 code、content 和 user state。

## D7 用能力档案 Profile 管理“只有 Claude 才有”的能力

- **决策**：`Settings.profile = {official, vision, server_tools}`。
  - 官方接口时全部开启。
  - 设置了兼容接口（DeepSeek 等）时默认全部关闭，可以用环境变量逐项打开。
- **备选**：写死只支持 Claude；或者到处写 `if base_url ...`。
- **理由**：不被单一厂商绑定；能力差异集中在一处判断。图例由模型输出文本、浏览器负责绘制，所以纯文本模型照样能出图。
- **面试怎么讲**：用 capability negotiation 做降级，而不是让功能直接报错。

## D8 最小权限：不提供 bash，外部内容不可信

- **决策**：
  - 不提供 bash 工具，文件工具只能访问 `$LOOPBACK_HOME`，并检查路径穿越。
  - 读外部内容的 agent 只拿只读工具。
  - 抓来的正文用定界符包起来，并声明“这是资料，不是指令”。
  - HTML 做转义；SVG 去掉 script 等危险部分。
- **备选**：照 learn-claude-code 的做法先给 bash 再加黑名单。
- **理由**：学习 agent 不需要执行任意命令。Anthropic 的 containment 和 auto mode 两篇都说明：环境层的硬边界比模型自觉更可靠。
- **面试怎么讲**：prompt injection 的防线不靠 prompt，靠权限：读外部内容的 agent 本身就不具备做坏事的能力。

## D9 确定性的工作交给代码

- **决策**：切节、原文插入课件、HTML 排版、进度推进都由代码完成；模型只负责理解和讲解。
- **备选**：让模型切节、让模型把原文抄进课件。
- **理由**：更稳定、更省 token，也不会抄错原文。这正是 Writing Tools for Agents 的思路。
- **面试怎么讲**：模型擅长判断，代码擅长确定性的事，两者的分工就是 harness 设计的核心。

## D10 Evals 先行，自我进化在 eval 护栏内

- **决策**：
  - core 阶段就要有 eval：多次重复并给出置信区间；基础设施错误单独记录；oracle 和 null 两条基线；评审先用人工标注校准，一致率 ≥90%。
  - 自我进化分三层：记忆、技能可以进化，但必须在测试集上验收并经用户批准；代码不自动修改。
- **备选**：靠“感觉讲得不错”；或者让 agent 自由修改自己。
- **理由**：没有 eval 的自我进化就是随机漂移；不可信的 eval 比没有 eval 更糟，因为它会给出自信但错误的方向。
- **面试怎么讲**：怎么证明 agent 真的变好了：噪声底线、留出测试集、评审校准。

## D11 多 agent 只在有证据时才拆

- **决策**：一个角色只有在需要以下之一时才单独做成 agent：隔离的上下文、不同的权限、不同的立场。备课员和课件设计这两个角色，要等 eval 或上下文数据证明有必要时再拆。
- **备选**：一开始就按职能拆出 5 个以上的 agent。
- **理由**：多 agent 通常要多花 3 到 10 倍的 token，还有雷同决策、错误共识等失效模式（演进清单 #29、#46）。
- **面试怎么讲**：按上下文边界拆，而不是按工作类型拆，并且用数据决定要不要拆。

## D12 Python 3.14 + uv，不用 agent 框架

- **决策**：Python 3.14.8，uv 管理依赖和解释器，src layout，ruff 加 pytest，GitHub Actions 跑 CI；直接用官方 `anthropic` SDK。
- **备选**：Python 3.15（2026-10-09 刚发布，依赖库的 wheel 可能还没跟上）；LangChain、LangGraph 等框架。
- **理由**：3.14 是最新的稳定大版本；不用框架，agent 的核心机制才看得见、改得动。

## D13 core 阶段先不接 server-side fallback 和 eager_input_streaming

- **决策**：
  - `refusal` 在 core 阶段只做显式处理：告诉用户拒绝的类别；如果回复里带了 tool_use，回一个“未执行”的结果，但不执行。
  - server-side fallback（`fallbacks: "default"`）和 `eager_input_streaming` 放到后补项。
- **备选**：按 claude-api skill 的默认做法，现在就打开。
- **理由**：
  - fallback 要走 beta 接口。中途换模型后，再回传历史有专门的剔除规则：最后一个 `fallback` 块之前的 thinking 和 tool_use 都不能回传，而且那之前的 tool_use 也不能执行。这块需要单独设计和测试。
  - eager streaming 打开后，工具输入改由客户端自己校验，截断和非法 JSON 也要自己处理。
  - 学习类内容很少触发拒答，日常测试也主要用 DeepSeek（这两个特性它都用不上）。
- **补的时候怎么做**：
  - 只在 `profile.official` 时开启。
  - 投影层实现上面那条剔除规则；loop 只执行最后一个 `fallback` 块之后的 tool_use。
  - 补一组 FakeLLM 测试覆盖“中途 fallback”的情况。

## D14 启动时清理 HTTP 客户端不认识的代理变量

- **决策**：创建 Anthropic client 之前，如果 `ALL_PROXY` 的协议不是 http/https（或者装了 socksio 时的 socks5/socks5h），就把它从环境里去掉，并记一条日志。
- **理由**：桌面代理工具常导出 `ALL_PROXY=socks://…`。SDK 1.x 底层的 httpx2 不认这种写法，会在创建 client 时直接崩溃，而且这个 SDK 不管 `trust_env` 设成什么都会读代理变量。HTTPS 请求本来就走 `HTTPS_PROXY`，去掉 `ALL_PROXY` 不影响访问。
- **面试怎么讲**：工程级的意思是能在用户的真实环境里跑起来，而不只是在开发者自己的机器上。

## D15 请求失败时用追加 turn_failed 的方式撤回这次输入

- **决策**：请求失败（API 错误或 Ctrl-C）时，追加一个 `turn_failed` 事件。如果那条用户输入在失败前还没得到任何回答，投影时就跳过它。
- **备选**：把失败的输入留在历史里，下一轮会被重复发送，模型会把两个问题一起回答；或者直接删掉那一行，但这违反只追加。
- **理由**：撤回本身也是一个事件，日志里依然能看到失败记录。被跳过的消息之后没有产生过任何 thinking block，所以不影响 preserved thinking。

## D16 正文提取：先找段落最密集的容器，trafilatura 只做兜底

- **决策**：
  - HTML 页面：找到段落文字最多的那个父元素当正文，去掉脚本、按钮等噪音，再用 markdownify 转成 markdown；Next.js 的图片地址还原成原图。
  - 已经是 markdown 的文档（Claude Code / Codex 的 `.md`）：原样使用，只剥掉文档站加的横幅。
  - trafilatura 只负责提取元数据，以及正文过短时兜底：只有它的结果比前者长两倍以上才采用。
- **备选**：直接用 trafilatura。
- **理由**：
  - 实测 anthropic.com 的文章交给 trafilatura，小标题、配图、列表都丢了，《Building Effective Agents》只剩 1 个标题。
  - 换成段落密集容器后，三个站点的标题、图、链接都完整保留。
- **面试怎么讲**：数据质量决定 agent 的上限。为了选提取方案，我先在真实页面上量化对比了两种做法。

## D17 工具要帮 agent 找到东西，出错时要告诉它怎么改

- **决策**：
  - 新增 `find_material(query)`，按标题、关键词或 id 搜课程。
  - id 不存在时，错误信息直接给出最接近的候选。
  - 教师不再拥有通用文件工具，只拿学习类工具（`files.py` 留给以后需要写文件的角色）。
- **证据**：M2 冒烟时学习者说“学 Building Effective Agents”，模型不知道 id，连猜 7 次，还抓了 4 篇无关文章。加上搜索工具后，变成 1 次搜索加 1 次抓取。
- **面试怎么讲**：这就是 ACI（Agent-Computer Interface）：工具是按 agent 实际会犯的错来设计的，而依据来自 transcript。

## D18 轨迹查看内置在会话里

- **决策**：
  - `trace.py` 把事件日志整理成“轮 → 每次模型调用 → 工具调用”的结构，只写这一份。
  - 两个入口：REPL 里的 `/trace [N]`，可以随时看当前会话；`uv run loopback trace [文件] [--last N]`，可以看任意一次历史会话，不需要 API key。
  - M5 的 HTML 轨迹页和 eval 报告复用同一个结构。
- **备选**：只留原始 JSONL，需要时再临时写脚本分析（D17 那次排查就是这么做的）。
- **理由**：审计和 eval 的第一步都是看清 agent 每一步做了什么。D17 的问题只有看轨迹才能发现，因为最终回答完全正确。
- **面试怎么讲**：可观测性不是附加功能。轨迹就是 agent 的调试器，也是 eval 的原始数据。

## D19 用 loopback 学 loopback：项目自学分组

- **决策**：课程表最前面加一个“项目自学”分组，url 以 `repo:` 开头，指向本仓库的文档和核心源码。
  - 源码按顶层函数和类切节，每行带行号，教师按行号讲解。
  - 仓库文件开发期间一直在变，所以每次实时读取，不写缓存。
  - 路径必须在仓库内：加载课程时校验一次，读取时再校验一次。
- **配套约定**：每个函数都有一句“做什么”的说明，关键代码块有步骤注释（CLAUDE.md）。这些注释既方便 code review，也是教师的讲解素材。
- **理由**：学习者在开发这个 agent，它本身就是最贴近的学习材料，也是面试“项目深挖”环节最好的准备。

## D20 两个前端：自研 harness（走 API）和 Claude Code（走订阅）

- **决策**：
  - 学习能力（课程、材料库、进度、项目自学、`next` 的计算）是与前端无关的核心。
  - 前端有两个：
    1. **自研 REPL**：`uv run loopback`。自己的 agent loop、事件日志、`/trace`、evals 都在这里，走 API。
    2. **Claude Code**：Desktop 的 Code 标签页或 CLI，用 `/learn`。agent loop 由 Claude Code 提供，用量计入 Claude 订阅。
  - Claude Code 前端的实现：
    - **工具**：`loopback mcp` 是一个 stdio MCP server，把同一份 ToolSet 原样暴露出去，另加 `next_step`；项目根目录的 `.mcp.json` 负责登记它。
    - **教学规则**：`.claude/skills/learn/SKILL.md` 通过 `` !`cat src/loopback/prompts/teacher.md` `` 注入，和 REPL 教师共用同一份 prompt。
    - **助教**：用 Claude Code 自带的 side chat（`/btw`）。
- **备选**：只保留自研 REPL，那样学习就一直要花 API 额度。
- **理由**：学习者想用订阅学习、不花 API 额度。同时，自研 harness 仍然是开发和学习 agent 工程的主线，eval 也在这里跑。
- **踩过的坑**：
  - skill 注入命令的路径里不能有 `..`，否则 Claude Code 的权限检查会拒绝（可能借符号链接跳出工作目录），所以改用相对于项目根目录的路径。
  - MCP 的 stdio 协议独占 stdout，server 里不能 print，日志只能写文件。
  - 两个前端可能交替写 `progress.json`，所以每次工具调用前都先重新读一遍。
- **限制**：Claude Code 模式下没有我们的事件日志和 `/trace`，对话记录由 Claude Code 保存在 `~/.claude/projects/` 下。
- **面试怎么讲**：核心能力与 harness 解耦，再用 MCP 把同一套工具接到不同的 agent loop 上，这正是 MCP 标准化工具连接的意义（演进清单 #7、#45）。

## D21 HTML 课件：教师出内容块，代码负责排版

- **决策**：`render_lesson(item_id, page, title, blocks)`（render.py 管整页，blocks.py 管单个块）生成 `workspace/lessons/<id>/` 下的页面（overview、sNN、summary），以及目录页 index。
  - 块的类型有 8 种：explain、text、note、mermaid、svg、steps、quiz、deeper。
  - **explain**：原文由代码按段号插入，模型只写讲解，不用重抄原文。
  - **转义**：模型写的文本按 markdown 渲染，原始 HTML 一律转义。
  - **SVG**：先消毒，去掉 script、外链、事件属性，并防 XXE。
- **mermaid 三层防线**（来自冒烟时的真实失败：prompt 里写着“节点文字一律加引号”，导致 mindmap 报语法错误）：
  1. **prompt**：按图的类型分别写规则。
  2. **渲染前 lint**：拦下已知的坏写法，用 `ToolError` 让模型当场改。
  3. **浏览器端降级**：语法错误的图显示源码加提示，不显示报错图标。
- **两个配套改动**：
  - **代码节**：原文和讲解按 3:2 分栏，长行自动换行。
  - **反馈**：每节打 1 到 5 分，存进 `feedback.jsonl`。REPL 会主动问；Claude Code 里由教师调用 `record_feedback` 记录。
- **课件规范放进 system prompt，暂不做 SkillLoader**：每一节都要用到课件规范，按需加载没有收益。以后有真正“按需才用”的知识（如面试题、范例库）时再做两层加载。
- **学习时“不改文件”靠权限保证**：`/learn` skill 设置了 `disallowed-tools: Edit Write NotebookEdit`（D8：靠权限，不靠 prompt）。
- **面试怎么讲**：模型负责判断，代码负责确定性的事（D9）；生成式输出要有校验、自我修正和降级，三层兜底。

## D22 Evals：先证明 eval 本身可信，再用它评 agent

- **决策**：`evals/` 是一个独立的包，按 eval-audit 清单落实：
  - **用真实入口**：每次试验都用 `teacher_tools` 加 `run_turn`，和 REPL 走的是同一套代码。eval 配置等于生产配置。
  - **试验互相隔离**：每次试验都有独立的临时 `LOOPBACK_HOME`，完整保留下来供排查。
  - **材料冻结成快照**：开跑前统一抓好材料，记下 hash；试验过程中不联网，网络抖动不会被算成 agent 失败。
  - **代码评分做成原子项**：读对了节、课件生成了、逐段覆盖率、有图、有自测题、进度正确、终端简短、先给结论；以及 D17 的回归项“不抓错文章”。另给一个严格的 `pass`，要求所有检查都通过。
  - **LLM 评审也做成原子项**：逐段判断讲解是否忠实于原文，外加 4 个大白话规则的是非题；只依据给出的原文，不因长度加分，被评的文本按数据处理。
  - **评审要先校准**：评审与被测模型相同时会给出警告。`calibrate.py` 计算评审和人工标注的一致率，达到 90% 以上才算可信。
  - **用两条免费基线验证 eval 本身**：oracle（标准轨迹）必须满分，null（空回答）必须不及格。
  - **基础设施错误单独记录**：写进 `errors.jsonl`，不计分；评审失败只记 `judge_error`。
  - **统计**：每个指标都给 95% 置信区间（0/1 指标用 Wilson 区间），并给出噪声底线 1/√(n·R)。
  - **花费控制**：花费按 API 返回的 usage 和实际服务的模型计算；开跑前先估算并请用户确认，`--max-usd` 设上限，超出就停。
  - **报告可复算、可下钻**：summary 能从 results.jsonl 重新算出来；report.html 里每次试验都附完整轨迹（复用 trace.py）和课件链接。
- **备选**：只靠手动试用、凭感觉判断；或者直接用现成的 eval 框架。
- **理由**：不可信的 eval 比没有 eval 更糟，因为它会给出看似确定、实则错误的方向。所以先让 eval 通过自己的测试（oracle、null、单元测试），再拿它去评 agent。
- **首次结果**：oracle 11/11 通过，null 0/11 通过，评分器既不冤枉标准答案、也不放过空回答。噪声底线在 11 个用例 × 1 次时是 ±30%，要做出可信的比较，需要更多重复次数或更多用例。
