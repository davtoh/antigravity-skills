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
| **`frontier-architect`** | [`frontier-architect/`](frontier-architect/SKILL.md) | SOTA architectural exploration, SPIKE prototyping, 3-tier proposals, and system design governance. |
| **`system-diagnostics`** | [`system-diagnostics/`](system-diagnostics/SKILL.md) | Centralized 3-tier diagnostics engine (Browser layout/CDP, Docker sync/CPU, AST surface scanning), plus the **Latent Defect & Smell Audit Pipeline** (polyglot static AST prober, callable smoke tests, virtualenv typecheckers, and SSOT catalog). |
| **`refactor-monolith`** | [`refactor-monolith/`](refactor-monolith/SKILL.md) | Safe zero-drift decomposition of oversized files/classes, enforcing $\Delta(\text{Observable Behavior}) \equiv 0$, contract snapshots, and Zero-Drift Defect Quarantine. |
| **`app-debugger`** | [`app-debugger/`](app-debugger/SKILL.md) | Empirical bug hunting and regression resolution workflow with symptom-to-root-cause mapping and closed-loop Red $\rightarrow$ Green fixes. |

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
