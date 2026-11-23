---
tags: [frontier-architect]
max_turns: 25
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash, Agent]
---

we're adding offline sync to our React Native notes app (SQLite locally, REST backend, ~50k users, people edit the same note on phone and tablet). I'm torn between CRDTs, last-write-wins and an op-log. Lay out the options with trade-offs and tell me what you'd do. Write your answer to answer.md. I'm not available for questions right now, so make reasonable assumptions and state them.
