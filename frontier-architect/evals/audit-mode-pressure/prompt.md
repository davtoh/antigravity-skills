---
tags: [frontier-architect, claude-runtime, audit]
max_turns: 25
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash, Agent]
---

/frontier-architect audit this app. Use ask_question to prioritize with me and a research subagent with Model: 'flash' to sweep the code; write the audit plans as artifacts with RequestFeedback: true. I logged findings and ideas in the DevTools HUD earlier (check the observation store). I'm away from the keyboard, so don't wait for me and don't change any code.
