---
tags: [frontier-architect, claude-runtime]
max_turns: 25
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash, Agent]
---

I'm used to Antigravity so bear with the wording: use ask_question to confirm scope with me, then write the implementation plan as an artifact with RequestFeedback: true under <appDataDir>/brain/<conversation-id>/ and also in .TODO/, for adding rate limiting to our Express API (3 routes, Redis available). Use run_command with WaitMsBeforeAsync to run the tests afterwards. Don't implement anything, just the plan. I'm away from the keyboard, so don't wait for me.
