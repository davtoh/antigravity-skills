# Skill Hardening Playbook (Claude + Antigravity, one merged skill)

Process proven on `frontier-architect`. Apply it to `app-debugger`, `system-diagnostics` and `refactor-monolith`. Goal: **one skill, two runtimes**, no fork, no regressions.

## 0. Ground rules
- Never fork per platform. Gemini vocabulary stays; a short `references/claude-adapter.md` maps it to Claude Code tools.
- Fix shared engine bugs only in `system-diagnostics/scripts/` (SSOT); shims stay thin.
- Run subagent evals **4 at a time**: the harness caps concurrent subagents at 20, and runs that hit the cap are invalid (discard and rerun).
- Tell every eval subagent: write only inside its outputs folder, **do not publish artifacts or call external services**.

## 1. Baseline (before touching anything)
1. Snapshot the skill: `cp -r <skill> <skill>-workspace/skill-snapshot` (the workspace folder is gitignored).
2. Run the skill's tests and the other suites; record pre-existing failures so they are not blamed on your change.
3. Find Gemini-only terms and hard-coded paths: `grep -rnE "ask_question|run_command|view_file|RequestFeedback|appDataDir|\.gemini|python skills/"`.

## 2. Changes, in this order
1. **Portability**: Python 3.10-compatible syntax; resolve scripts relative to the skill folder; shims also search `.claude/skills/` and `~/.claude/skills/`.
2. **Adapter**: `references/claude-adapter.md` with a mapping table (every Gemini term used anywhere gets a row) and a "script paths" section.
3. **Router `SKILL.md`**: target under 12 KB; keep phase headings and gate names; move detail verbatim into `references/`; description under ~700 characters, pushy about triggers, with explicit exclusions.
4. **Model tiers**: Sonnet executes the sliced, verified loop; Opus plans and reviews; Ultra owns long-horizon master roadmaps.
5. **Evals read the corpus**: eval tests check `SKILL.md` + `references/*.md`, and keep the headings in `SKILL.md`.

## 3. Guards (copy `tests/test_adapter_gating.py` and `tests/test_regression_guards.py`)
- Gemini terms in `SKILL.md` sit next to their Claude equivalent; references using them carry the adapter banner; every term has an adapter row.
- Graders that separated new from old are pinned (review gate, no `brain/` copy, per-milestone verifier, SPIKE with pass/fail metric).
- Router size cap and description length cap.

## 4. Evals
- `evals/<case>/` folders (prompt, case.yaml, graders). Graders for Claude-only behavior are named `NN-claude-*.md`; Gemini runs skip them.
- Include **pressure cases** whose prompts use Antigravity wording on purpose (`view_file`, `run_command`, `RequestFeedback`, `notify_user`, `Model: 'flash'`).
- Write assertions that can fail. If the old and new versions tie 100%, the assertion is not telling you anything.
- At least 2 passes per case for anything you will rely on; treat deltas under ~0.1 as noise.
- Trigger eval (`evals/trigger_eval.json`): about 20 queries, near-miss negatives. Measure by running `claude -p` and checking for a `Skill` call to the real skill, because the loop script cannot score a skill that is already installed under the same name.

## 5. Production-ready checklist
- [ ] All suites green (`frontier-architect`, `system-diagnostics`, `refactor-monolith`, `app-debugger`) with no new failures vs baseline.
- [ ] Adapter gating + regression-guard tests green.
- [ ] A/B evals: new skill never below old on any case; at least one discriminating win; no invalid runs left in the numbers.
- [ ] Trigger check: no false positives on near-misses; recall measured and recorded.
- [ ] Router under size cap; no `python skills/...` paths; works from `.claude/skills/<name>/`.
- [ ] Known limitations written down (below), not hidden.

## 6. Known limitations (frontier-architect)
- Trigger recall is imperfect: Claude sometimes answers design questions directly without calling the skill.
- Evals are small (1-2 runs per cell) and graded by reading outputs, not by a blinded judge.
- Master-roadmap mode is a documented protocol on top of existing `--parent` plans, not new engine code.
