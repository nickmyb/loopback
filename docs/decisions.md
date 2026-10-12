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
