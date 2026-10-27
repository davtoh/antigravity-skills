# ⚡ Antigravity Skills

Curated, portable skill runbooks and procedural workflows for the [Google Antigravity](https://antigravity.google) AI pair-programming agent.

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

## 🛠️ Curated Repository Skills

| Skill | Directory | Description |
| :--- | :--- | :--- |
| **`frontier-architect`** | [`frontier-architect/`](frontier-architect/SKILL.md) | SOTA architectural exploration, SPIKE prototyping, and system design. |

---

## 📄 License
MIT License. Created by [davtoh](https://github.com/davtoh).