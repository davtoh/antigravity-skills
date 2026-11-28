# ⚡ Antigravity Skills

Curated, portable skill runbooks, diagnostics, and procedural workflows for the [Google Antigravity](https://antigravity.google) AI pair-programming agent.

---

## 🧠 Why On-Demand Skill Management?

Antigravity operates on **progressive disclosure**:
- Every installed skill injects its `name` and `description` into the agent's system prompt on **every single interaction** (~50–120 tokens per skill).
- The full procedure (`SKILL.md`) and bundled scripts load only when triggered.
- Statically installing dozens of skills drains context tokens and creates triggering conflicts.

**Best Practice:** Keep core skills curated here, and install specialized skills on demand using central managers or standalone installers.

---

## 📦 Installation & Skill Management

### 1. Central Skill Manager
Manage, search, install, and uninstall skills on demand without context bloat using:
👉 [**antigravity-skill-manager**](https://github.com/davtoh/antigravity-skill-manager)

```bash
# Search for skills
skill-manager search "session report"

# Install on demand
skill-manager install skill-creator

# List active skills
skill-manager list-installed
```

### 2. Standalone Utilities with Built-in Skill Installers
These standalone repositories provide full CLI tools alongside automated `--install-skill` flags:

- 📱 [**flutter-bluestacks-connector**](https://github.com/davtoh/flutter-bluestacks-connector)
  - Connects BlueStacks 5 to Android SDK ADB, eliminating daemon reset collisions.
  - Install skill: `python bluestacks_connector.py --install-skill`
- 🧹 [**git-history-purger**](https://github.com/davtoh/git-history-purger)
  - Inspects and purges large historical blobs from Git repos with automatic safety bundles.
  - Install skill: `python purge_git_history.py --install-skill`

---

## 🛠️ Curated Repository Skills & Capabilities

| Skill | Directory | Description & Key Capabilities |
| :--- | :--- | :--- |
| **`frontier-architect`** | [`frontier-architect/`](frontier-architect/SKILL.md) | SOTA architectural exploration, SPIKE prototyping, 3-tier proposals, and dual-track plan execution (`plan_engine.py` `discover`/`init`/`status`/`next`/`verify`/`advance --note`/`retrospective`/`digest`), with Claude Code adapter (`references/claude-adapter.md`). |
| **`system-diagnostics`** | [`system-diagnostics/`](system-diagnostics/SKILL.md) | Centralized 3-tier SSOT diagnostics engine (`diagnose.py`): Browser CDP (`ui --eval-file`), Docker sync/CPU (`container`), AST surface (`surface`), polyglot defect scanner (`scan`), bounded `changelog {add,migrate,show,status,pr-description}`, `transcript-audit`, `debug-retro`, `arch-map`, `run`/`traces`, and standalone `.skill` packager (`package-skill`). |
| **`refactor-monolith`** | [`refactor-monolith/`](refactor-monolith/SKILL.md) | Safe zero-drift decomposition of oversized files/classes, enforcing $\Delta(\text{Observable Behavior}) \equiv 0$, contract snapshots, and Zero-Drift Defect Quarantine. |
| **`app-debugger`** | [`app-debugger/`](app-debugger/SKILL.md) | Empirical bug hunting and regression resolution workflow with symptom-to-root-cause mapping, `debug-retro` logging, and closed-loop Red $\rightarrow$ Green fixes. |
| **`skill-creator`** | [`skill-creator/`](skill-creator/SKILL.md) | Iterative skill authoring, `evals/evals.json` benchmarking, description triggering optimization, and `.skill` packaging. |

---

## 📋 Changelog, PR Descriptions & Plan Telemetry

Recent tooling upgrades connect branch changelogs, `.TODO/` plans, and session retrospectives into a single low-token workflow:

- **PR Description Generator (`diagnose.py changelog pr-description`)**: Builds a structured GitHub PR Markdown body (or `--json` payload) from branch commits (`--base main`), `git diff --stat`, bounded `CHANGELOG.md` / `.changelogs/` archive shards (`--recent 5`), and `.TODO/<slug>.md` milestone headings & verification lines (`--plan <slug>`).
- **Milestone Notes & Workspace Learning Digest (`plan_engine.py`)**: `plan_engine.py advance --note "<summary>"` records milestone completion notes in `.frontier/state.json`; `plan_engine.py digest <slug> --backfill --write-scaffold` generates both plan `LEARNING_SCAFFOLD.md` and workspace `.frontier/LEARN_QUEUE.md`.
- **Transcript & Debug Telemetry (`diagnose.py`)**: `transcript-audit` computes deterministic step/retry/failure counts, `- REDIRECT` switches, `schedule-while-subagent` flags, and rubric `suggested_grade_cap`; `debug-retro --plan <slug>` logs `DEBUG_RETRO.md` and links `followup_cids`.

```bash
# Pre-run verification: run skill self-tests & eval suites
python -m unittest discover -s skills/system-diagnostics/tests -p "test_*.py"
python -m unittest discover -s skills/frontier-architect/tests -p "test_*.py"
```

| Scenario / Objective | Mode / Inputs | Key Parameters | Exact Runnable Command |
| :--- | :--- | :--- | :--- |
| **Generate PR Description** | Branch, changelog & plan | `--base --plan --recent` | `python skills/system-diagnostics/scripts/diagnose.py changelog pr-description --base main --plan <slug> --recent 5 --path .` |
| **Record Milestone & Commit Snippet** | Any repo (`<=150L` log) | `--title --type --summary --verify` | `python skills/system-diagnostics/scripts/diagnose.py changelog add --title "<Title>" --type feat --summary "<Summary>" --verify "<Cmd>" --path .` |
| **Advance Plan Milestone with Note** | Active `.TODO/` plan | `--milestone --note` | `python skills/frontier-architect/scripts/plan_engine.py advance <slug> --milestone <N> --note "<Summary>" --root .` |
| **Generate Learning Digest & Queue** | Completed plan / workspace | `--backfill --write-scaffold` | `python skills/frontier-architect/scripts/plan_engine.py digest <slug> --backfill --write-scaffold --root .` |
| **Audit Conversation Transcripts** | Brain logs (`--latest` / `--cids`) | `--latest 1 --json` | `python skills/system-diagnostics/scripts/diagnose.py transcript-audit --latest 1 --json` |
| **Log Debug Retrospective** | Post-fix debug session | `--plan --symptom --cause --status` | `python skills/system-diagnostics/scripts/diagnose.py debug-retro --plan <slug> --symptom "..." --cause "..." --status verified --cid <cid>` |
| **Generate Architecture Map** | Single root or subpaths | `--path --json` | `python skills/system-diagnostics/scripts/diagnose.py arch-map --path . --json` |
| **Package Standalone `.skill` Bundles** | Distribution | `all --out dist/` | `python skills/system-diagnostics/scripts/diagnose.py package-skill all --out dist/` |

---

## 🔬 Latent Defect & Code Smell Protocol

The repository implements a synchronized **Triad Separation of Concerns** for static defect discovery and resolution:

1. **Unified Read-Only Front Door (`system-diagnostics`)**:
   - `diagnose.py audit`: Static linter, virtualenv typecheck, platform import smell, and callable smoke scanner.
   - `diagnose.py scan`: Polyglot AST/lexer defect scanner across Python, JS/TS, CSS, and Dart with Dual-Key addressing (`DEFECT-001` + `DEF-<RULE>-<6HEX>`).
2. **Zero-Drift Quarantine (`refactor-monolith`)**:
   - During structural decomposition, discovered bugs are never fixed in-flight ($\Delta\text{Behavior} \equiv 0$). They are quarantined directly into `.diagnostics/defect_catalog.json`.
3. **Dual-Track Remediation**:
   - **Track A (Tactical / Surgical) $\rightarrow$ `/app-debugger`**: JIT test synthesis (`tests/quarantine/test_<id>.py`) for Red $\rightarrow$ Green fixes.
   - **Track B (Structural / Architectural) $\rightarrow$ `/frontier-architect` + `/grill-me`**: Socratic 3-tier redesign for systemic race conditions, modularity overruns, and state management flaws.

---

## 📄 License
MIT License. Created by [davtoh](https://github.com/davtoh).
