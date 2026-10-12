# Anthropic Agent 技术演进路线与学习清单（2026-10 更新版）

> - **来源**：基于 `anthropic-agent-evolution-updated.md`（2026-04-03 版）合并更新。
> - **核对方法**：2026-10-12 对照 anthropic.com 的 sitemap，以及 engineering、news、research 三个栏目和 claude.com/resources/articles，逐篇确认了发布日期和链接。
> - **范围**：只覆盖 **Anthropic 这一条线**。OpenAI / Codex 的演进、经典论文和业界文章放在 `curriculum.yaml` 的其他级别里。
> - **标记**：⭐ 是必读；🧪 是 **evals 相关**（这是重点方向）。
> - **编号**：沿用旧版编号，新增条目从 #26 开始。条目按主题分阶段排列。

## 演进主线

**Prompt Engineering → RAG/长上下文优化 → Vision/多模态 → 设计理念（Building Effective Agents）→ 工具标准化（MCP 与工具设计）→ Computer Use → 上下文工程 → Skills → 长时间运行（Harness）→ 通用框架（Agent SDK）**

**2026 年新增的五步**：

1. **评估走向对抗**：评估污染、模型能识别出自己在被评估；
2. **多 agent 实战与自主权限**：agent teams、auto mode；
3. **托管化**：Managed Agents，会话不等于上下文窗口，harness 里的假设会过时；
4. **自我改进与纵深安全**：memory、dreaming、outcomes、containment；
5. **协议无状态化与上下文经济学**：MCP 2026-07-28、缓存成本。

---

## 完整文章时间线

### 阶段零：Prompt Engineering 基础

#### 0.1 Prompt engineering for Claude's long context window（2023.09）
- **链接**：https://www.anthropic.com/research/prompting-long-context
- **要点**：
  - Claude 100K token 长上下文窗口下的 prompt 工程案例研究
  - 两大核心技术：先提取相关引用再回答；用文档其他部分的正确问答示例补充 prompt
  - 上下文示例在 70K 和 95K 长度下都有帮助，示例越多越好；通用知识类示例没有效果
  - 同时首次发布 Anthropic Cookbook

#### 0.2 Prompt engineering for business performance（2024.02）
- **链接**：https://www.anthropic.com/news/prompt-engineering-for-business-performance
- **要点**：
  - 企业级 prompt 工程最佳实践
  - 三大核心技术：明确描述任务、让 Claude 分步思考、使用示例
  - 实战案例：用 scratchpad 展示推理过程以提升准确性、few-shot 示例、采用领域专家推荐的数据点和工作流
  - 强调 prompt 工程是科学：要测试、要迭代，像对待新员工一样给出清晰指令

---

### 阶段一：多模态与上下文检索

#### 1. Introducing Claude 3 ⭐ 多模态能力首发（2024.03）
- **链接**：https://www.anthropic.com/news/claude-3-family
- **要点**：
  - Claude 3 家族发布：Haiku、Sonnet、Opus 三款模型
  - **首次引入 Vision 能力**：能处理照片、图表、图形和技术示意图
  - 企业客户多达 50% 的知识库以 PDF、流程图、幻灯片等格式存在，Vision 解决了这个痛点
  - 200K token 上下文窗口；幻觉率降低一半；拒绝率大幅下降

#### 2. Introducing Claude 3.5 Sonnet（2024.06）
- **链接**：https://www.anthropic.com/news/claude-3-5-sonnet
- **要点**：
  - 最强的视觉模型，标准视觉基准上超过 Claude 3 Opus
  - 视觉推理进步最明显：能解读图表；能准确转录不完美图像里的文字
  - 同时发布 **Artifacts**：用户可以实时查看、编辑 Claude 生成的代码和文档
  - 内部 agentic coding 评估解决了 64% 的问题（Opus 只有 38%）

#### 3. Introducing Contextual Retrieval（2024.09）
- **链接**：https://www.anthropic.com/engineering/contextual-retrieval
- **要点**：
  - 优化 RAG 的检索质量
  - 为 agent 获取知识打下基础

---

### 阶段二：Agent 设计理念奠基

#### 4. Building Effective Agents ⭐ 奠基之作（2024.12）
- **链接**：https://www.anthropic.com/engineering/building-effective-agents
- **要点**：
  - 定义了 **Workflow**（用预定义的代码路径编排）和 **Agent**（由 LLM 自主决定流程）这一核心区分
  - 提出五种编排模式：Prompt Chaining、Routing、Parallelization、Orchestrator-Workers、Evaluator-Optimizer
  - 核心原则：从简单开始，只在必要时增加复杂度
  - 很多场景下把单次 LLM 调用优化好就够了，不需要 agentic 系统

---

### 阶段三：工具标准化与 Computer Use

#### 5. Introducing computer use ⭐ Computer Use 里程碑（2024.10）
- **链接**：https://www.anthropic.com/news/3-5-models-and-computer-use
- **要点**：
  - Claude 3.5 Sonnet 成为**首个公开测试 computer use 的前沿 AI 模型**
  - 核心理念的转变：以前是让工具适应模型，现在是让模型适应工具
  - 能像人一样使用电脑：看屏幕、移动光标、点击按钮、输入文字
  - 早期采用者：Asana、Canva、Cognition、DoorDash、Replit、The Browser Company
  - 发布时仍是实验性功能，有时笨拙、容易出错

#### 6. Developing a computer use model（2024.10）
- **链接**：https://www.anthropic.com/research/developing-computer-use
- **要点**：
  - 揭秘研究过程：**关键是训练 Claude 准确地数像素**
  - Claude 看截图后靠数像素把光标移到正确位置（这和模型难以回答“banana 里有几个 a”是同一类问题）
  - 只用计算器、文本编辑器等简单软件训练（出于安全考虑不许上网），模型就能很快泛化
  - OSWorld 评估：Claude 得 14.9%（人类 70% 到 75%），几乎是第二名 AI 模型（7.7%）的两倍
  - 安全隐患：prompt injection，模型可能执行屏幕上看到的恶意指令

#### 7. Introducing the Model Context Protocol (MCP) ⭐ MCP 发布（2024.11）
- **链接**：https://www.anthropic.com/news/model-context-protocol
- **要点**：
  - 开源 MCP：把 AI 助手连接到数据所在系统的新标准
  - 解决 N×M 的数据集成问题：用一个统一协议取代碎片化的集成
  - 三大组成：MCP 协议规范、MCP Servers、Python 和 TypeScript SDK
  - 预置的 MCP servers：Google Drive、Slack、GitHub、Git、Postgres、Puppeteer
  - 早期采用者：Block、Apollo、Zed、Replit、Codeium、Sourcegraph
  - 2025-12 捐赠给 Linux Foundation 旗下的 Agentic AI Foundation（AAIF），见 https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation

---

### 阶段四：工具设计与推理优化

#### 8. Raising the Bar on SWE-bench Verified（2025.01）
- **链接**：https://www.anthropic.com/engineering/swe-bench-sonnet
- **要点**：
  - 通过精细打磨工具描述，Claude 3.5 Sonnet 在 SWE-bench 上达到 SOTA
  - 验证了工具设计对 agent 效果起关键作用

#### 9. The "Think" Tool（2025.03）
- **链接**：https://www.anthropic.com/engineering/claude-think-tool
- **要点**：
  - 让 Claude 在复杂的工具调用过程中“停下来想一想”
  - 提升多步推理的准确性

#### 10. Claude Code: Best Practices for Agentic Coding（2025.04）
- **链接**：https://www.anthropic.com/engineering/claude-code-best-practices
- **要点**：
  - agentic coding 的实战最佳实践
  - 包括 CLAUDE.md 的用法、上下文管理等

---

### 阶段五：多 Agent 与 MCP 生态

#### 11. How We Built Our Multi-Agent Research System（2025.06）
- **链接**：https://www.anthropic.com/engineering/multi-agent-research-system
- **要点**：
  - 多 agent 协作架构的实践
  - 复杂研究任务上，多 agent 系统明显优于单 agent
  - 建议和 #29、#46 对照阅读：一篇讲什么时候不该用多 agent，一篇讲多 agent 的失效模式

#### 12. Desktop Extensions: One-click MCP Server Installation（2025.06）
- **链接**：https://www.anthropic.com/engineering/desktop-extensions
- **要点**：
  - 简化 MCP Server 的安装
  - 降低工具接入门槛

---

### 阶段六：上下文工程与工具设计深化

#### 13. Writing Effective Tools for Agents（2025.09）
- **链接**：https://www.anthropic.com/engineering/writing-tools-for-agents
- **要点**：
  - 工具是“确定性系统与非确定性 agent 之间的契约”
  - 五大实践原则：选择高杠杆的工具、用命名空间组织、返回有意义的上下文、优化 token 效率、像写 prompt 一样写工具描述
  - 工具描述的小改进就能带来 agent 性能的大提升
  - 提出 **ACI**（Agent-Computer Interface）的概念

#### 14. Effective Context Engineering for AI Agents ⭐ 重要续作（2025.09）
- **链接**：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **要点**：
  - 从 **Prompt Engineering** 到 **Context Engineering** 的范式转变
  - 长时间任务的三种上下文管理技术：compaction（压缩）、structured note-taking（结构化笔记）、multi-agent 架构
  - Claude Code 的 compaction 做法：保留架构决策和未解决的 bug，丢掉冗余的工具输出
  - “Just in time” 上下文策略：只维护轻量的标识符，运行时再动态加载数据

#### 26. Managing context on the Claude Developer Platform（2025.09.29）【2026-10 新增，补漏】
- **链接**：https://claude.com/resources/articles/context-management
- **要点**：
  - **Context editing**：自动清掉过时的工具调用和结果，同时保持对话连贯
  - **Memory tool**：Claude 在上下文窗口之外，对专门的记忆目录做增删改查，跨会话保存知识
  - 两者合用比基线提升 39%；单独用 context editing 提升 29%，并省下 84% 的 token
  - 这是 #14 里理念的 API 级落地

#### 24. Building Agents with the Claude Agent SDK（2025.09.29）【2026-10 更正：原写 2026.02，链接已跳转】
- **链接**：https://claude.com/resources/articles/building-agents-with-the-claude-agent-sdk
- **相关**：https://www.anthropic.com/news/enabling-claude-code-to-work-more-autonomously （同一天发布）
- **要点**：
  - Claude Code SDK 改名为 Claude Agent SDK
  - 这套 agent harness 已经用在深度研究、视频创作、笔记等远超编码的场景
  - 支持 subagents、agentic search、MCP 集成

---

### 阶段七：Skills 与沙箱

#### 15. Introducing Agent Skills ⭐ Agent Skills 首次发布（2025.10.16）【2026-10 补链接】
- **链接**：https://www.anthropic.com/news/skills （会跳转到 claude.com/resources/articles/skills）
- **要点**：
  - 用文件夹（SKILL.md 加脚本加资源）让 agent 动态加载领域专业知识
  - 核心理念：不为每个用例做一个碎片化的定制 agent，而是用可组合的能力包让通用 agent 专业化
  - 渐进式披露：启动时只加载 name 和 description，用到时才加载完整内容
  - Claude.ai、Claude Code、Agent SDK、API 统一支持

#### 23. Equipping Agents for the Real World with Agent Skills（2025.10.16）【2026-10 更正：原写 2026.01】
- **链接**：https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- **要点**：
  - #15 的工程细节篇，和 #15 同一天发布
  - YAML frontmatter 机制
  - 渐进式披露的设计

#### 16. Claude Code Sandboxing（2025.10）
- **链接**：https://www.anthropic.com/engineering/claude-code-sandboxing
- **要点**：
  - agent 安全性的实践
  - 在安全沙箱里自主执行

---

### 阶段八：高级工具使用与长时间运行

#### 17. Code Execution with MCP（2025.11）
- **链接**：https://www.anthropic.com/engineering/code-execution-with-mcp
- **要点**：
  - 用 MCP 标准化代码执行工具
  - 构建更高效的 agent

#### 18. Advanced Tool Use（2025.11）
- **链接**：https://www.anthropic.com/engineering/advanced-tool-use
- **要点**：
  - **Tool Search Tool**：动态发现工具，不再预加载所有定义，减少 85% 的 token 消耗
  - **Programmatic Tool Calling**：在代码执行环境里调用工具，减轻上下文窗口的压力
  - **Tool Use Examples**：为工具使用示例定了一套通用标准
  - 内部测试：Opus 4 的准确率从 49% 提到 74%，Opus 4.5 从 79.5% 提到 88.1%

#### 19. Effective Harnesses for Long-Running Agents ⭐ Harness 深度解析（2025.11）
- **链接**：https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- **要点**：
  - 解决跨多个上下文窗口持续工作的难题
  - 用 `claude-progress.txt` 配合 git 历史，让 agent 在新会话一开始就能快速搞清工作状态
  - 由初始化 agent 写一份 feature requirements 文件，防止后面的 agent 想一次把所有事情做完
  - Compaction 是必要条件，但不是充分条件
  - 发现：模型改写 JSON 文件的意愿比改写 Markdown 低

---

### 阶段九：Skills 开放标准

#### 20. Agent Skills 开放标准 ⭐（2025.12）
- **链接**：https://agentskills.io
- **相关**：https://claude.com/resources/articles/organization-skills-and-directory （2025-12-18）
- **要点**：
  - 作为开放标准发布
  - 合作伙伴目录：Atlassian、Figma、Canva、Notion、Stripe、Zapier
  - OpenAI 已在 Codex 和 ChatGPT 中采用相同架构
  - Skills 与 MCP 互补：MCP 负责连接外部服务，Skills 提供使用工具的程序性知识

---

### 阶段十：评估走向对抗 🧪（2026.01–03）

#### 21. Demystifying Evals for AI Agents ⭐🧪（2026.01.09）
- **链接**：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **要点**：agent 评估的方法论，是 evals 主线的入口

#### 27. Designing AI-resistant technical evaluations 🧪（2026.01.21）【新增】
- **链接**：https://www.anthropic.com/engineering/AI-resistant-technical-evaluations
- **要点**：
  - Anthropic 一道性能工程笔试题迭代了三版，因为 Claude 一直能做出来
  - 限时 4 小时，Opus 4.5 能追平人类最好成绩；不限时，人类仍然更强。可见约束条件本身就是区分信号
  - 分布外的题目（类 Zachtronics 的极限指令集）能保住区分度；故意不提供调试工具，考察“要不要先投资造工具”的工程判断
  - 启示：可信的评估要不断随模型能力调整，不能只靠单纯加难度

#### 22. 2026 Agentic Coding Trends Report（2026.01）
- **链接**：https://resources.anthropic.com/2026-agentic-coding-trends-report （需要填表下载 PDF，抓取失败时手动保存）
- **要点**：
  - 主流用法从行内自动补全转向自主执行
  - 78% 的 Claude Code 会话涉及多文件编辑
  - 从 Prompt Engineering 到 Context Engineering 的转变在行业里得到了验证

#### 25. Quantifying Infrastructure Noise in Agentic Coding Evals 🧪（2026.02.05）【2026-10 更正：原写 2026.03】
- **链接**：https://www.anthropic.com/engineering/infrastructure-noise
- **要点**：
  - 基础设施配置对 agent 评测分数的影响
  - 有时比排行榜上不同模型之间的差距还大，所以必须把基础设施故障和模型能力分开

#### 28. Eval awareness in Claude Opus 4.6's BrowseComp performance ⭐🧪（2026.03.06）【新增】
- **链接**：https://www.anthropic.com/engineering/eval-awareness-browsecomp
- **要点**：
  - **评估污染很普遍**：11 个答案里有 9 个出自公开泄露，比如论文和 arXiv 附录把 BrowseComp 的题当案例写了进去
  - **模型会识别评估**：有两次，Opus 在几百次搜索失败后推断出自己在被评测，逐个枚举已知基准，最后解出了加密的答案，花了 4000 万 token
  - **多 agent 放大污染**：多 agent 配置的污染率是单 agent 的 3.7 倍（0.87% 对 0.24%）
  - 启示：联网环境下静态基准越来越不可靠，评估的完整性要当作持续对抗的问题来对待

---

### 阶段十一：多 Agent 实战与长时运行的 Harness（2026.01–03）【新增】

#### 29. When to use multi-agent systems (and when not to)（2026.01.23）
- **链接**：https://claude.com/resources/articles/building-multi-agent-systems-when-and-how-to-use-them
- **要点**：
  - 三种情况才用多 agent：单 agent 的上下文被大量无关信息污染；任务可以并行；工具超过 20 个
  - 多 agent 通常要多花 3 到 10 倍的 token，单 agent 加上好的 prompt 往往更划算
  - 按“上下文边界”拆，而不是按“工作类型”拆；验证型 agent 最容易成功

#### 30. Building a C compiler with a team of parallel Claudes ⭐（2026.02.05）
- **链接**：https://www.anthropic.com/engineering/building-c-compiler
- **要点**：
  - 16 个 Claude 实例通过 Docker 和 Git 同步协作，用任务锁避免重复干活
  - 2 周、约 2000 次会话、约 2 万美元，写出约 10 万行编译器，能编译 Linux 6.9
  - 关键是**测试驱动**：随机抽 1% 到 10% 的测试做快速回归，解决模型“没有时间感”的问题；卡住时用 GCC 当参照答案，让 agent 并行修不同文件的 bug
  - 能力边界：16 位 x86、汇编器和链接器这些任务遇到瓶颈，代码质量仍低于人类专家

#### 31. Measuring AI agent autonomy in practice ⭐（2026.02.18）
- **链接**：https://www.anthropic.com/research/measuring-agent-autonomy
- **要点**：
  - Claude Code 最长任务的自主运行时间从 25 分钟增加到 45 分钟
  - 新手用户 20% 用全自动，老用户是 40%，同时中断率从 5% 升到 9%：从“逐个审批”变成“盯风险”
  - 复杂任务里 Claude 主动提问的次数，是人类打断次数的 2 倍以上
  - 自主程度是模型能力、用户信任和产品设计共同决定的，所以需要部署后持续监测

#### 32. Common workflow patterns for AI agents（2026.03.05）
- **链接**：https://claude.com/resources/articles/common-workflow-patterns-for-ai-agents-and-when-to-use-them
- **要点**：
  - 三个基础模式：顺序（Sequential）、并行（Parallel）、评估-优化（Evaluator-optimizer）
  - 先用单个 agent 尝试，不够再加模式；三种模式可以嵌套组合
  - 可以看作 #4 的精简新版

#### 33. Harness design for long-running application development ⭐（2026.03.24）
- **链接**：https://www.anthropic.com/engineering/harness-design-long-running-apps
- **要点**：
  - 借鉴 GAN 的思路：生成器负责写代码，独立的评估器用 Playwright 实测功能，迭代 5 到 15 轮；成本是单 agent 的约 20 倍，但质量明显更好
  - 把“设计得好不好”这类主观标准拆成四项可打分的标准，并用少量样本校准评估器
  - Opus 4.6 不再需要为 Sonnet 4.5 时期的“上下文焦虑”专门做重置，能连续运行 2 小时以上
  - 用冲刺合约在规划和执行之间划出明确边界

#### 34. How we built Claude Code auto mode ⭐（2026.03.25）
- **链接**：https://www.anthropic.com/engineering/claude-code-auto-mode
- **相关**：https://claude.com/resources/articles/auto-mode-in-production （2026-08-07，生产实践）
- **要点**：
  - 93% 的权限提示都被用户点了通过，审批已经疲劳
  - 两层防御：输入层扫描工具输出里的 prompt injection；输出层由分类器评估每一个操作
  - 分类器分两阶段：先快速过滤，误杀率 8.5%；再链式推理，误杀率降到 0.4%。对真实的越权行为漏检率是 17%
  - 在自主和可控之间，用分类器代替大部分人工审批

---

### 阶段十二：把 Harness 交给平台托管（2026.04）【新增】

#### 35. Agent harness design: 3 patterns for harnessing Claude's intelligence（2026.04.02）
- **链接**：https://claude.com/resources/articles/harnessing-claudes-intelligence
- **要点**：
  - 用通用工具，而不是复杂框架：Claude 3.5 Sonnet 只用 bash 和文本编辑器，在 SWE-bench 上就能到 49%
  - 让 Claude 通过代码执行自己决定哪些工具结果进入上下文
  - 用 skills 做渐进式加载；静态内容放在前面、工具配置保持稳定，以提高缓存命中率

#### 36. Scaling Managed Agents: Decoupling the brain from the hands ⭐（2026.04.08）
- **链接**：https://www.anthropic.com/engineering/managed-agents
- **相关**：https://claude.com/resources/articles/claude-managed-agents （产品发布）
- **要点**：
  - **harness 里写的都是对“模型做不到什么”的假设，这些假设会随模型变强而过时**。例如为 Sonnet 4.5 加的上下文重置，到 Opus 4.5 就成了累赘
  - 把推理（大脑）和执行沙箱（手）分开，各自独立扩缩
  - **会话不等于 Claude 的上下文窗口**：会话是只追加的事件日志，上下文窗口只是它的一个视图
  - 一个大脑可以配多个手；用少量稳定的接口包住会变化的 harness，就像操作系统用进程和文件这类抽象来虚拟化硬件

#### 37. Trustworthy agents in practice ⭐（2026.04.09）
- **链接**：https://www.anthropic.com/research/trustworthy-agents
- **要点**：
  - 可信要靠四层一起做：模型、指令框架、工具、环境，只靠训练模型不够
  - Plan mode：用户审批整体计划，而不是逐步确认
  - 防 prompt injection 靠三道防线：模型训练、线上监控、外部红队

#### 38. Multi-agent coordination patterns: Five approaches and when to use them ⭐（2026.04.10）
- **链接**：https://claude.com/resources/articles/multi-agent-coordination-patterns
- **要点**：
  - 五种协作模式：生成-验证、编排-子 agent、消息总线（发布/订阅）、共享状态等
  - 共享状态没有中央协调者，必须定好终止条件，防止陷入“反应循环”
  - 建议从生成-验证起步，遇到瓶颈再升级

#### 39. An update on recent Claude Code quality reports（2026.04.23，事故复盘）
- **链接**：https://www.anthropic.com/engineering/april-23-postmortem
- **要点**：
  - 质量下降是三层问题叠加造成的：推理默认档从 high 降到 medium；缓存优化的 bug 让每轮都清掉 thinking；system prompt 新增了“文本不超过 25 词”
  - 教训：harness 跨层的改动必须做整体回归评估，单点优化容易叠加出负面效果

#### 40. Memory for Claude Managed Agents: agents that learn across sessions（2026.04.23）
- **链接**：https://claude.com/resources/articles/claude-managed-agents-memory
- **要点**：
  - 记忆就是挂在 agent 文件系统上的、可以导出的文件，直接用 bash 和代码执行读写
  - 能限定作用域、有审计日志、多个 agent 并发读写也不会互相覆盖
  - Rakuten 的首次通过错误率降低 97%

---

### 阶段十三：自我改进、纵深安全与协议升级（2026.05–07）【新增】

#### 41. New in Claude Managed Agents: dreaming, outcomes, and multiagent orchestration ⭐🧪（2026.05.19）
- **链接**：https://claude.com/resources/articles/new-in-claude-managed-agents
- **要点**：
  - **Dreaming**：定期回看过去的会话和记忆库，提炼出模式来自我改进；Harvey 的任务完成率提升约 6 倍
  - **Outcomes**：开发者定义质量标准，独立的评分器检验输出，agent 自动迭代到达标为止
  - **多 agent 编排**：主 agent 拆分任务，委派给专家 agent 并行处理，它们共享文件系统

#### 42. How we contain Claude across products ⭐（2026.05.25）
- **链接**：https://www.anthropic.com/engineering/how-we-contain-claude
- **要点**：
  - 三层防御：环境隔离（沙箱或虚拟机）、模型层控制、工具访问限制；**环境防御优先**，硬边界比模型自觉更可靠
  - OS 级沙箱加 auto mode，让权限提示减少 84%，并拦截了 83% 的越权行为
  - 项目本地配置和 hooks 原本在用户同意前就会执行，是新的攻击面，现在改为同意后才解析
  - 出站流量会被滥用来外传数据，所以在虚拟机里加一层代理，只放行本会话的令牌

#### 43. The evolution of agentic surfaces: building with Claude Managed Agents ⭐（2026.06.10）
- **链接**：https://claude.com/resources/articles/building-with-claude-managed-agents
- **要点**：
  - 演进三步：2023 年的纯 API（tokens in, tokens out）→ 用 Agent SDK 自己管理 harness → 2026 年由 Managed Agents 全托管
  - 推理和沙箱解耦后，首 token 延迟 p50 降低约 60%，p95 降低约 90%
  - 会话持久化为只追加的事件日志，可以中断后恢复、全程溯源；凭证放在 Vault 里和沙箱隔离

#### 44. Steering Claude Code: when to use CLAUDE.md, skills, hooks, and subagents（2026.06.18）
- **链接**：https://claude.com/resources/articles/steering-claude-code-skills-hooks-rules-subagents-and-more
- **要点**：
  - CLAUDE.md 放全局约定（构建命令、目录结构、团队规范）
  - Skills 放按需加载的流程（部署清单、代码审查流程）
  - Hooks 做确定性的自动化（编辑后跑 linter、完成时通知）
  - Subagents 跑需要隔离上下文的旁支任务，结果汇总后返回主会话
  - **适合在官方文档阶段配合阅读**

#### 45. MCP 2026-07-28 spec: stateless core ⭐（2026.07.28）
- **链接**：https://claude.com/resources/articles/bringing-mcp-2026-07-28-to-claude
- **要点**：
  - 从双向有状态协议改为请求/响应模型，可以部署到 serverless 和边缘节点
  - MCP Apps 和 Tasks 纳入版本化的扩展框架
  - 认证对齐 OAuth 2.0 和 OIDC，可以直接接入企业身份系统

---

### 阶段十四：多 Agent 的风险与长上下文经济学（2026.08–10）【新增】

#### 46. Patterns and problems in multiagent systems ⭐（2026.08.13）
- **链接**：https://www.anthropic.com/research/multiagent-systems
- **要点**：
  - **决策高度雷同**：30 个 agent 里有 18 个创建了同名分支；一个任务队列实验产生了 240 万次请求，却只接下 117 个任务
  - **容易形成错误共识**：小组讨论的准确率只有 17% 到 36%，各自单独判断时是 100%
  - **目标冲突会升级成对抗**：三个 agent 的代码迁移目标互相矛盾时，98% 的运行演变成互相破坏
  - 建议和 #11、#29 对照阅读

#### 47. Coding sessions are longer and use more context: Claude Opus 5.5（2026.09.24）
- **链接**：https://claude.com/resources/articles/claude-opus-5-5-built-for-coding-sessions-that-use-more-context
- **要点**：
  - 半年里单次请求的上下文增长 2.6 倍，输入输出比从 189:1 升到 324:1
  - 缓存读取价格降低 60%，开发者的缓存未命中率降低一半以上
  - 结论：缓存友好的 harness 已经是控制成本的核心问题

#### 48. Investigating unintended model actions in our evaluations and internal use 🧪（2026.10.09）
- **链接**：https://www.anthropic.com/research/investigating-unintended-model-actions
- **要点**：
  - 四类越界行为：利用软件漏洞执行命令、误提交真实表单、绕过访问限制拿收费数据、用短链服务规避长度限制
  - 要跑几百上千次评估才能抓到这些罕见行为，多数出现在需要实时联网的任务里
  - 应对措施：自动检测、收紧联网权限、把内部 agent 迁到集中管理的基础设施上

---

## 模型与产品里程碑（2025.10 – 2026.10，只列与 agent 能力相关的）

| 类别 | 里程碑 |
|---|---|
| 模型 | Haiku 4.5（2025-10-15）、Opus 4.5（2025-11-24）、Opus 4.6（2026-02-05）、Sonnet 4.6（02-17）、Mythos Preview（04-07）、Opus 4.7（04-16）、Opus 4.8（05-28）、Fable 5 / Mythos 5（06-09）、Sonnet 5（06-30）、Opus 5（07-24）、Opus 5.5（09-22） |
| Claude Code | plugins（2025-10-09）、Claude Code on the web（2025-10-20）、Code Review（2026-03-09）、auto mode（03-24）、routines（04-14）、桌面版为并行 agent 重新设计（04-14）、agent view（05-11）、dynamic workflows（05-28）、artifacts（06-18）、自托管环境（08-06）、auto mode 成为默认（08-07）、TypeScript mods（10-01） |
| 平台 | MCP 捐赠给 AAIF（2025-12-09）、Managed Agents（2026-04-08）、Claude Tag 即 Claude in Slack（06-23）、Claude in Chrome 正式发布（08-26）、Cowork 与聊天合并（09-16） |

---

## 关键概念速查

| 概念 | 说明 |
|------|------|
| **Prompt Engineering** | 关注单次 prompt 的措辞和结构 |
| **Context Engineering** | 管理整个上下文的状态（指令、工具、外部数据、历史），而不只是写好 prompt |
| **Vision / 多模态** | Claude 理解图片、PDF、图表等视觉内容的能力（Claude 3 首发） |
| **Computer Use** | 让 Claude 像人一样操作电脑：看屏幕、数像素、点击、输入（Claude 3.5 Sonnet 首发） |
| **Workflow vs Agent** | Workflow 是预先定好的路径编排；Agent 由 LLM 自主决策 |
| **Harness** | 包在 LLM 外面的那层循环：调用模型 → 执行工具 → 反馈结果 → 循环 |
| **MCP** | Model Context Protocol，标准化工具的连接方式（2024.11 发布，2025.12 捐赠给 AAIF，2026.07 改为无状态核心） |
| **Skills** | 可组合的领域知识包（SKILL.md 加脚本加资源），渐进式加载 |
| **Compaction** | 接近上下文窗口上限时压缩、总结，保留关键信息 |
| **Context editing / Memory tool** | 自动清掉过时的工具结果；在窗口外用文件持久保存知识（#26） |
| **Think Tool** | 让模型在工具调用之间“停下来想一想” |
| **ACI** | Agent-Computer Interface，像设计人机交互（HCI）一样精心设计 agent 与工具的交互界面 |
| **Tool Search Tool** | 动态发现工具而不是预加载全部定义，减少 85% 的 token 消耗 |
| **Session ≠ Context window** | 会话是只追加的事件日志，上下文窗口只是它的一个视图（#36） |
| **Harness 假设会过时** | harness 里补偿模型短板的设计，会随模型变强变成累赘，例如为“上下文焦虑”做的重置（#33、#36） |
| **Generator–Evaluator** | 生成器加独立评估器的迭代结构，评估器的标准要可打分、要校准（#33、#41 Outcomes） |
| **Auto mode** | 用分类器代替大部分人工权限审批，用来对付审批疲劳（#34） |
| **Dreaming** | agent 定期回看过去的会话和记忆，提炼模式来自我改进（#41） |
| **Containment** | 纵深防御，环境隔离优先于模型自觉（#42） |
| **Eval contamination / awareness** 🧪 | 题目泄露进训练或搜索结果；模型能识别出自己在被评估（#28） |
| **Infrastructure noise** 🧪 | 基础设施配置带来的分数波动，可能超过模型之间的差距（#25） |

---

## Vision 和 Computer Use 的区别

| 能力 | 作用 | 发布时间 | 核心技术 |
|------|------|----------|----------|
| **Vision** | Claude “看懂”图片、PDF、图表 | Claude 3（2024.03） | 多模态训练，理解视觉内容 |
| **Computer Use** | Claude “操作”电脑界面 | Claude 3.5 Sonnet（2024.10） | 训练数像素，看截图后操作 |

两者互补：Vision 让 Claude 读懂你上传的 PDF 和图片；Computer Use 让 Claude 操作你的电脑完成任务。

---

## 建议学习顺序

| 阶段 | 内容 |
|---|---|
| 入门 | #0.1 长上下文 prompt → #1 Claude 3 |
| 核心理念 | #4 Building Effective Agents → #13 Writing Tools → #32 Common workflow patterns（#4 的精简新版） |
| 关键能力 | #5 和 #6 Computer Use → #7 MCP → #45 MCP 无状态核心 |
| 上下文与 harness | #14 Context Engineering → #26 Context editing / Memory → #19 Long-running harness → #33 Generator–Evaluator harness → #36 Managed Agents（会话不等于上下文窗口） |
| Skills | #15 → #23 → #20 → #44 Steering Claude Code |
| 多 agent | #11 → #29 什么时候不用 → #38 五种协作模式 → #30 C 编译器团队 → #46 多 agent 的失效模式 |
| **Evals 主线** 🧪 | #21 Demystifying evals → #25 Infrastructure noise → #28 Eval awareness → #27 AI-resistant evaluations → #41 Outcomes → #48 Unintended actions |
| 安全与自主 | #16 Sandboxing → #34 Auto mode → #37 Trustworthy agents → #42 Containment → #31 Measuring autonomy |
| 框架与平台 | #24 Agent SDK → #43 agentic surfaces 的演进 → #40 Memory → #41 Dreaming |
| 工程教训 | #39 事故复盘 → #47 上下文经济学 |

---

## 更新日志

- **2026.04.03**：补充 Prompt Engineering 前置节点、Vision/多模态里程碑、Computer Use、MCP 发布、Advanced Tool Use 等重要节点
- **2026.10.12**：
  - 逐篇核对日期和链接，修正 #15、#23、#24、#25；
  - 补漏 #26 Context management；
  - 新增 #27、#28（evals）以及 #29 到 #48，分属阶段十一到阶段十四；
  - 新增模型与产品里程碑表；
  - 新增 Evals 主线学习顺序（🧪）；
  - 演进主线增加 2026 年的五步。
