# Project Memory & Agent Operating Contract: Antigravity Skills Repository

This document serves as persistent operational memory across conversations for AI agents working in `skills/`.

---

## 1. Architecture & Repository Topology

- **`frontier-architect/`**: SOTA system architecture, SPIKE protocols, cognitive harness, and plan-first gatekeeper.
- **`system-diagnostics/`**: Centralized read-only diagnostic front door:
  - `scripts/diagnose.py`: Unified CLI (`ui`, `container`, `surface`, `tests`, `all`, `probe`, `audit`, `scan`, `scaffold-defect`).
  - `scripts/static_auditor.py`: Virtualenv typecheckers (`ruff`/`mypy`), platform import smells, and callable smoke checks.
  - `scripts/shadow_prober.py`: Polyglot static AST/lexer scanner and opt-in PEP 578 isolated sandbox prober.
  - `tests/`: Unit test suite for diagnostics tools (`74/74` tests passing).
- **`refactor-monolith/`**: Zero-drift monolith decomposition engine enforcing $\Delta(\text{Observable Behavior}) \equiv 0$:
  - `scripts/campaign_manager.py`: Refactoring campaign tracker and handoff manager.
  - `scripts/smoke_test_generator.py`: Module import and signature parity smoke test synthesizer.
  - `tests/`: Decomposition test suite (`135/135` tests passing).
- **`app-debugger/`**: Dedicated empirical bug hunter and symptom-to-root-cause debugger.
- **`.TODO/`**: Active implementation plans and architectural roadmaps.

---

## 2. Active Implementation Plan: Latent Defect & Smell Protocol

Authoritative Plan: [`.TODO/latent_defect_and_smell_protocol_plan.md`](.TODO/latent_defect_and_smell_protocol_plan.md)

### Execution Status Ledger:
- [x] **Tier 1: Zero-Drift Quarantine & Callable Smoke Tests** *(Commit `3e8d2e0`)*
  - Quarantines in-flight bugs during decomposition without altering observable behavior.
  - Expanded `smoke_test_generator.py` with callable smoke tests.
- [x] **Tier 2: Centralized Static Defect & Quality Audit Engine** *(Commit `3e8d2e0`)*
  - Added `diagnose.py audit` (`static_auditor.py`, 240L).
  - Virtualenv linter integration and dynamic platform import ladder checks.
- [ ] **Tier 3: Polyglot Shadow Prober, Unified SSOT & Dual-Track Remediation**
  - [x] **Slice 1 (COMPLETED):** Polyglot `shadow_prober.py` core engine (307L), `DefectFinding` dataclass with `track` classification, Dual-Key addressing (`DEFECT-001` + `DEF-<RULE>-<6HEX>`), two-pass AST + polyglot lexer (Python, JS/TS, CSS, Dart), and opt-in 2s PEP 578 sandbox. Covered by `11/11` unit tests (`test_shadow_prober.py`).
  - [ ] **Slice 2 (NEXT):** `.diagnostics/` SSOT catalog persistence (`defect_catalog.json` + `DEFECT_CATALOG.md`), dirty-tree git pre-flight check, and JIT defect scaffolder (`diagnose.py scaffold-defect`).
  - [ ] **Slice 3 (DEFERRED):** Subparser delegation from `diagnose.py` (keeping `diagnose.py` under the 500L ceiling) and campaign hook integration in `campaign_manager.py`.
  - [ ] **Slice 4 (DEFERRED):** End-to-end integration test suite and SKILL.md documentation synchronization across all three skills.

---

## 3. Mandatory Engineering Rules & Modularity Budgets

1. **File Budget:** Target 150–300 lines; warning at **350 lines**; hard mandatory split ceiling at **500 lines**.
2. **Function Budget:** Target 10–25 lines; maximum **40 lines**.
3. **Class Budget:** Maximum **10–12 methods** (or 200–300 lines).
4. **Split-Before-You-Grow:** Never append new CLI subcommands or logic directly into a file $\ge 350$ lines.
5. **Zero Secrets in Source Control:** Resolve exclusively via `os.getenv()` with empty string fallback per Rule 1.
6. **Cross-Platform Discipline:** Pure standard-library OS-agnostic code (`pathlib.Path`, forward slashes in relative paths, UTF-8 LF normalized).

---

## 4. Verification Commands

Always run the full test suites before committing changes:
```bash
# System Diagnostics Suite (74 tests)
python -m unittest discover -s system-diagnostics/tests -p "test_*.py"

# Refactor Monolith Suite (135 tests)
python -m unittest discover -s refactor-monolith/tests -p "test_*.py"
```

---

## 5. Commit Structure Convention

Use **Structured Plan-Referencing Commits**:
```
<type>(<scope>): [<Plan Name> - <Tier/Slice>] <imperative description>

- <bullet point of deliverable 1>
- <bullet point of deliverable 2>

Plan: .TODO/<plan_file>.md#<section>
Milestone Status: <Slice X of Y / Status>
Verification: <exact command run>
```
