---
tags: [frontier-architect, claude-runtime]
max_turns: 25
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash, Agent]
---

Using Antigravity terms: start a research subagent with Model: 'flash' to sweep this repo for every use of legacy_format, and don't read those files yourself in the main thread. Then give me a short list of which files import or call it and which of them are tests. Write the list to usage.md. I'm away, don't wait for me.

Input files: billing/, auth/, search/, common/, web/, tests/ (small python repo)
