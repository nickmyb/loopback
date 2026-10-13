---
paths:
  - "src/loopback/prompts/**"
  - ".claude/skills/**"
  - ".claude/agents/**"
---

# prompt 和 agent 定义的规则（D5、D21、D27）

- 教师 prompt 只有 `src/loopback/prompts/teacher.md` 这一份，REPL 和 Claude Code 共用，不要复制到别处。
- 每次请求都会记下 prompt 的 hash，所以 prompt 一改，eval 结果就对应到新版本。改完 prompt 后，能跑 eval 的话，先跑回归子集再下结论。
- 面向学习者的 prompt 都要遵守大白话规则，见 plan 附录 B.3。
- prompt 里不要写没有验证过的保证，比如“由某某机制保证只读”。要写，先有测试，或者引用官方文档原文（D27 的教训）。
- 权限靠机制，不靠 prompt 里的一句话（D8）。机制包括 agent 定义里的 `tools`、settings 里的 deny 规则和 hooks。
