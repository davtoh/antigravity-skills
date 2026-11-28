# Learning Proposal: Post-Mortem Improvements for `app-debugger` & Tooling

## Executive Summary

Across the three debugging conversations (`227fa4f4...`, `41f12285...`, and `0d15c6fc...`), the `app-debugger` workflow evolved from an uncontrolled sprawl of 17 scratch scripts in Conversation 1 to a highly disciplined, zero-scratch execution in Conversations 2 and 3. In Conversation 3, the agent pinpointed a subtle CSS scroll-snap offset defect ($13\text{px} > 4\text{px}$) and codified Section 7 into `security_and_standards.md`.

However, the three runs also revealed persistent, cross-cutting friction:
1. **File-Watcher & Terminal Collisions**: Modifying test files repeatedly triggered `uvicorn --reload` in the user's terminal, disrupting the server and flooding the user with browser permission prompts.
2. **Line-Ending Failures (`edit_file`)**: Every single conversation suffered multiple `edit_file` failures due to Windows CRLF vs LF mismatches.
3. **Background Task Polling**: Agents repeatedly polled `manage_task status` on backgrounded browser tasks rather than awaiting reactive wakeup.
4. **Tool Capability Gap**: `diagnose.py ui` lacked `--wait` and scroll-snap/window offset auditing, forcing the agent to use `cdp_inspect.py`.

---

## Proposed Changes

### Proposal 1: Update `app-debugger/SKILL.md` (Skill Refinement)

#### Rationale
Prevent live dev server interference, avoid polling loops, and eliminate CRLF mismatches before using `edit_file`.

#### Proposed Additions to `C:\Users\User\.gemini\config\skills\app-debugger\SKILL.md`

```markdown
### 5. Dev Server & File Watcher Safety
When running diagnostics against a live development server (e.g., Uvicorn, Vite, Next.js, Flask):
- **Avoid Modifying Watched Files Repeatedly**: Be aware that touching backend or test files in active directories triggers auto-reloaders (`StatReload`), which can abort live HTTP requests, drop active browser websockets, and hijack the user's terminal.
- **Batch Verification**: Group code edits atomically rather than incrementally triggering 10 reloads.
- **Respect User Approval**: If the user chose "Live Chrome Tab", bundle evaluations into single commands to avoid repeated permission dialogs. If repeated checks are required, switch to `--headless`.

### 6. Reactive Task Discipline
- Never call `manage_task status` in a loop. Background tasks wake up the agent reactively upon completion.
```

---

### Proposal 2: Update `system-diagnostics/scripts/diagnose.py` (CLI Tool Enhancement)

#### Rationale
In Conversation 2, the agent crashed by guessing `--wait 1.5`. In Conversation 1, `diagnose.py ui` gave a false pass because it did not audit `window.scrollX`. In Conversation 3, the agent had to bypass `run_diagnose.py` and invoke `cdp_inspect.py` directly.

#### Proposed Capabilities for `diagnose.py ui`
1. **Add `--wait <float>`**: Allow an explicit settle duration (in seconds) after load or click before taking bounding box measurements.
2. **Include Window Scroll in `--audit-layout`**: Assert `window.scrollX === 0` and `window.scrollY === 0`. If `scrollX > 0`, report a layout regression (catches `scrollIntoView` ancestor propagation).
3. **Resting Offset Inspection**: Report first child element `left` vs parent `left` to highlight scroll-snap resting gaps.

---

### Proposal 3: Windows Line-Ending Invariant (`python_decrufting.md` or `security_and_standards.md`)

#### Rationale
Across all 3 conversations, 9 separate tool errors occurred because `edit_file` received LF targets while Windows files had CRLF endings.

#### Proposed Addition to `security_and_standards.md` (Cross-Platform Compatibility)

```markdown
- **Line Ending Discipline on Windows**:
  - Before applying multi-line `edit_file` replacements on Windows repositories with `core.autocrlf = true`, verify file line endings (CRLF vs LF).
  - Normalize or match the target whitespace exactly to avoid `target content not found in the file` errors.
```

---

## User Review & Completed Elevation
- [x] Evaluated and elevated via `/frontier-architect` & `/skill-creator` standards
- [x] Implemented `--wait` settle parameter and `--strict` layout assertion in `diagnose.py` & `cdp_inspect.py`
- [x] Implemented window `scrollX`/`scrollY` auditing and element `offsetFromParent`/`scrollSnap` metadata in `audit_layout.js`
- [x] Synchronized CDP inspector and layout scripts to `frontier-architect/scripts/` to eliminate tool drift
- [x] Codified Line Ending Discipline into `rules/security_and_standards.md` (Section 5)
- [x] Updated `app-debugger/SKILL.md` with Dev Server & File Watcher Safety, Reactive Task Discipline, and CRLF inspection
- [x] Expanded `evals.json` with 2 new evaluation scenarios and updated `test_skill_evals.py` (all 13 tests passing)
- [x] Expanded unit test coverage in `system-diagnostics/tests/` (all 54 tests passing) and `frontier-architect/tests/` (all 20 tests passing)
