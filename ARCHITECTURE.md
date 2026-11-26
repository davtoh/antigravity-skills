# Current Architecture Map: Antigravity Skills Monorepo

**Snapshot:** branch `feature/add-debug-connectors` @ `7817b06` (built on `main` @ `6f02826`, which already contains the Claude hardening of `frontier-architect`, PR #5), 2026-11-26.
**Purpose:** let an agent (Claude or Gemini) learn every skill, script and capability in one read, and see what is broken, enhanced or missing for Claude. Read this instead of sweeping the repo.
**Evidence labels:** **[V]** = checked directly while writing this file; **[S]** = reported by read-only survey agents, not re-checked line by line. Refresh with the commands in section 10.

---

## 1. Topology and rules

| Skill | Role | Real engine code | Depends on |
| :--- | :--- | :--- | :--- |
| `system-diagnostics` | **SSOT** diagnostic front door (`diagnose.py`) | 33 Python + 2 JS scripts, ~7.4k lines [V] | none |
| `frontier-architect` | Architecture, plan-first execution, plan ledger (`plan_engine.py`) | `plan_*` family (10 files) | thin shims to system-diagnostics (`cdp_inspect.py`, `docker_audit.py`) |
| `app-debugger` | Symptom-to-root-cause debugging | `run_diagnose.py` (resolver only) | system-diagnostics via subprocess |
| `refactor-monolith` | Zero-drift monolith decomposition | 13 engine scripts | thin shims (`css_inspector.py`, `surface_scanners.py`) to system-diagnostics |

- **SSOT rule:** fix shared diagnostic bugs only in `system-diagnostics/scripts/` and its tests; never fork code into a shim. Shims are ~50 lines and load the SSOT module via `importlib`. [S]
- **Budgets:** files 150-300 lines target, 350 warn, 500 hard; functions <= 40 lines; classes <= 10-12 methods (`AGENTS.md`).
- `.TODO/` holds 11 committed plans (~75 KB); **do not load them by default**. Use `python "<skill_dir>/scripts/plan_engine.py" status|next`. [V: `discover`]
- `HARDENING_PLAYBOOK.md` is the process for making a skill work on both runtimes; `frontier-architect-workspace/` is a gitignored eval workspace.

## 2. How scripts are found (path resolution)

Run scripts relative to the skill folder, never `python skills/...`. Skills are usually installed as symlinks `~/.claude/skills/<name> -> <repo>/<name>` [V].

| Caller | Candidate order for the diagnostics engine |
| :--- | :--- |
| `frontier-architect/scripts/cdp_inspect.py`, `docker_audit.py` | `SYSTEM_DIAGNOSTICS_DIR` -> `../../system-diagnostics` -> `../system-diagnostics` -> `cwd/.claude/skills` -> `~/.claude/skills` -> `~/.gemini/config/skills` [S] |
| `refactor-monolith/scripts/css_inspector.py`, `surface_scanners.py` | `SYSTEM_DIAGNOSTICS_DIR` -> `../../system-diagnostics` -> `~/.gemini/config/skills` (**no `.claude`**) [S] |
| `app-debugger/scripts/run_diagnose.py` | `DIAGNOSE_CLI_PATH` -> `SYSTEM_DIAGNOSTICS_DIR` -> sibling `../../system-diagnostics` -> cwd and 3 parents (`skills/`, `.gemini/...`) -> `~/.gemini/...` (**no `.claude`**) [S] |
| `refactor-monolith/scripts/auxiliary_tool_bridge.py` | `.gemini` paths only for `diagnose.py` and frontier scripts (lines 32-40) [S] |

Sibling discovery means a normal side-by-side install still works under Claude even where `.claude` is not listed.

## 3. system-diagnostics (the SSOT engine)

`SKILL.md` 15.5 KB (over the 12 KB router target) [V]; commands live in `references/cli-reference.md`.

**Layers** [S] (lines in parentheses):
- **CLI front doors:** `diagnose.py` (309; dispatch dict at lines 283-300), `diagnose_cli.py` (178), `trace_cli.py` (93), `runtime_runner.py` (49).
- **Browser / CDP:** `cdp_inspect.py` (335), `cdp_transport.py` (217), `cdp_runtime.py` (128), `cdp_viewport.py` (87), `audit_layout.js` (313), `audit_layout_extra.js` (102), `css_inspector.py` (161).
- **Docker:** `docker_audit.py` (113).
- **Surface / AST scanners:** `surface_scanners.py` (**359**), `surface_verifier.py` (342), `surface_contracts.py` (329), `surface_layout_checks.py` (81), `arch_mapper.py` (327), `cross_module_rules.py` (323), `ast_guard_rules.py` (65), `signature_drift_rules.py` (117).
- **Defects, audit, probes:** `shadow_prober.py` (349), `defect_catalog.py` (346), `scaffold_templates.py` (198, *defect* templates, not connector templates), `static_auditor.py` (313), `probe_runner.py` (293) + `probes/camera_hardware.py`.
- **Runtime traces and connectors:** `trace_recorder.py` (282; `.diagnostics/trace_catalog.json` + daily `traces/trace_YYYYMMDD.jsonl`, `TRC-<type>-<hash>` fingerprints), `trace_middleware.py` (63), `connector_scaffolder.py` (150; writes `diagnostic_bridge.py` for fastapi/flask/generic), `bootstrap/sitecustomize.py` (24).
- **Changelog, transcripts, PR text:** `changelog_manager.py` (278), `changelog_archive.py` (144), `pr_description.py` (153), `transcript_auditor.py` (345), `transcript_checks.py` (134), `debug_retro.py` (169), `skill_packager.py` (166).

**`diagnose.py` subcommands** [S]: `ui`, `container`, `surface`, `tests`, `all`, `probe {list,run,new,save}`, `audit`, `scan`, `scaffold-defect`, `resolve-defect`, `dismiss-defect`, `changelog {add,migrate,show,status,pr-description}`, `traces` (actions `list|resolve`; flags `--scaffold {fastapi,flask,generic} --dest`), `run`, `package-skill`, `arch-map`, `transcript-audit`, `debug-retro`.

**New on this branch vs `main`** [S]: `changelog pr-description` (`pr_description.py`), multi-viewport audit (`cdp_viewport.py`), extra layout checks (`audit_layout_extra.js`), `SILENT_SHAPE_SKIP` rule (`ast_guard_rules.py`), probe status hardening (`INFRA_UNAVAILABLE`, empty-CDP-sweep downgrade), `App.navigate` target checks, TDD-failure handling in transcript audit. The branch does **not** touch `trace_*`, `connector_scaffolder.py` or `trace_cli.py`, despite its name.

**What does not exist yet** [V: grep + file checks]: any "observation" store, `observations` subcommand, trace correlation across requests, HUD asset, `assets/` folder, `observation_store.py`, `diagnostic_bridge.py` observation routes.

## 4. The other three skills

- **frontier-architect** [V tests, S layout]: router `SKILL.md` ~11.8 KB, 10 references (`claude-adapter.md`, `phase-protocols.md`, `plan-contracts.md`, `reasoning-harness.md`, `spike-protocol.md`, ...). Engine: `plan_engine.py` (342) with `plan_state` (348), `plan_digest` (**351**), `plan_scaffold` (321), `plan_telemetry` (305), `plan_cli_helpers` (259), `plan_verify` (218), `plan_parser` (200), `plan_rollup` (156), `plan_reconcile` (114). Evals: `evals.json` (29 evals) + 7 case folders + `trigger_eval.json`.
- **app-debugger** [S]: `SKILL.md` 11.5 KB (description ~735 chars), 2 references, `scripts/run_diagnose.py` (109, a resolver, not a shim). Evals: `evals.json` (14), **no `trigger_eval.json`**.
- **refactor-monolith** [S]: `SKILL.md` **16.3 KB** (description ~910 chars), 3 references. Engines over budget: `campaign_manager.py` (**470**), `auxiliary_tool_bridge.py` (**445**); others 335/318/300. State lives in `.refactor/`. Evals: `evals.json` (10) + `trigger_eval.json`.

## 5. Claude-readiness matrix

| Skill | Adapter / gating | Un-gated Gemini terms [S] | Verdict for Claude |
| :--- | :--- | :--- | :--- |
| `frontier-architect` | `claude-adapter.md` + `test_adapter_gating.py` + `test_regression_guards.py` | none un-gated | **Enhanced, guarded** |
| `app-debugger` | none | 49 (`ask_question` heading at SKILL.md:34, `RequestFeedback`, `python skills/app-debugger/...`, `.gemini`) | Works via sibling discovery; instructions assume Gemini tool names |
| `refactor-monolith` | none | 8 (`ask_question` in `language-playbooks.md:140`, `.gemini` paths, `python skills/...` hint in `campaign_manager.py:172`) | Works via sibling discovery; shims lack `.claude` |
| `system-diagnostics` | none | `python skills/system-diagnostics/...` in `SKILL.md` and `cli-reference.md` (~57 occurrences); `<appDataDir>/brain` (SKILL.md:41) | Engine is platform-neutral; docs and some defaults are Gemini-shaped |

**Capabilities that do not work under Claude today:**
- `transcript-audit` and `debug-retro` read the Antigravity layout `<brain>/<cid>/.system_generated/logs/transcript.jsonl` (default `~/.gemini/antigravity/brain`, env `AGY_BRAIN_DIR`) and match the `run_command` tool name [V]. They cannot read Claude Code session logs under `~/.claude/projects/`. The post-task transcript audit the skills call for is therefore unavailable on Claude.
- `package-skill` looks for `skill-creator` only under `~/.gemini/config/skills/` (`skill_packager.py:75`); `probe_runner.py:51` global probe dir is `~/.gemini/...`; scaffolded `diagnostic_bridge.py` tries `~/.gemini/config/skills/system-diagnostics/scripts` on `sys.path` [S].
- `scaffold_templates.py:69-71` prints `python skills/system-diagnostics/scripts/diagnose.py ...` hints that only work from this repo's root [S].

**This branch introduced no Claude regression** that I found: its new files are platform-neutral and the test failures below are the same as before the branch. [V for tests]

## 6. Tests, evals and status (measured 2026-11-26, after the cross-platform test fixes) [V]

| Suite | Tests | Result | Notes |
| :--- | :--- | :--- | :--- |
| `frontier-architect/tests` | 140 | **OK** | includes adapter gating, regression guards, Claude install layout |
| `system-diagnostics/tests` | 264 | **OK** | 4 previously failing tests fixed: they built paths from an unresolved macOS temp dir |
| `refactor-monolith/tests` | 159 | **OK** | `test_discover_virtualenv` fixed the same way |
| `app-debugger/tests` | 24 | **OK** | `test_resolve_python_*venv` fixed the same way |

**Rule learned:** in tests, always `Path(tempfile...).resolve()` and compare paths with `.resolve()` on both sides. macOS `/var` is a symlink to `/private/var`; `unittest` and the engines return real paths. Resolving is a no-op on Windows, so the same tests pass on Gemini/Antigravity and Claude.

Scripts with no direct test [S]: `connector_scaffolder`, `changelog_archive`, `surface_layout_checks`, `runtime_runner`, `scaffold_templates`, `ast_guard_rules` (indirect only), `pr_description` and `skill_packager` (CLI-level only), `trace_cli` (via `test_cross_module_rules`).

## 7. In-flight work: Universal Debug Observation Connector

Plan: `.TODO/universal_debug_observation_connector_plan.md`, rewritten 2026-11-26 as a **master roadmap** (4 milestones, M1 active). Child plan for Milestone 1: `.TODO/step_1_observation_store_cli.md` (7 tasks, function-level design). Both register and parse with `plan_engine`. Milestones: (1) observation store, correlation reader and `diagnose.py observations` CLI; (2) DevTools HUD assets, preceded by a SPIKE; (3) `recording_id` stamping in the trace middleware and the `--with-observations` scaffolder flag (also fixes the generated bridge so it finds the engine under `.claude/skills`); (4) skill docs and Claude/Gemini parity. The master file holds the intent ledger, decisions, data, CLI, HUD, correlation, security and parity contracts. **Status: not implemented.**

## 8. Documentation that is stale or inconsistent [S]
- `README.md`: Antigravity-only branding, `python skills/...` commands, test commands only for two skills.
- `AGENTS.md`: verification block omits `app-debugger`.
- `frontier-architect/tests/README.md`: says 28 scenarios / 125 assertions / "115+" tests; reality is 29 / 129 / 140. It also lists test files that do not exist and a `skills/skill-creator` path that is not in this tree.
- Playbook targets not yet met: `refactor-monolith` SKILL.md 16.3 KB, `system-diagnostics` 15.5 KB, descriptions over ~700 chars for `refactor-monolith` and `app-debugger`.

## 9. Open risks for agents
1. Files at or over the soft budget: `surface_scanners.py` 359, `plan_digest.py` 351, `shadow_prober.py` 349, `plan_state.py` 348, `defect_catalog.py` 346, `transcript_auditor.py` 345. Do not append to these; split first.
2. All four suites are green, so a full-suite verifier is valid again. Keep it that way: any new test that compares temp paths must resolve them.
3. `connector_scaffolder.py` has no direct tests, yet it is the base for planned work.

## 10. Refreshing this file
```bash
git log --oneline main..HEAD ; git diff --stat main...HEAD
for s in system-diagnostics refactor-monolith frontier-architect app-debugger; do python3 -m unittest discover -s $s/tests -p "test_*.py" 2>&1 | grep -E "^(FAIL:|ERROR:|Ran |OK|FAILED)"; done
wc -l */scripts/*.py | sort -rn | head -25
grep -rnE "ask_question|run_command|view_file|RequestFeedback|appDataDir|\.gemini|python skills/" --include=*.md --include=*.py . | grep -v workspace | wc -l
python3 frontier-architect/scripts/plan_engine.py discover --root .
```
