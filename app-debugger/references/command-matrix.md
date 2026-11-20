# App Debugger Command Matrix & Diagnostic Recipes

Consult this reference during **Step 2 (Reproduce First)** for copy-pasteable commands, pre-run verification checks, and the skill directory layout.

> When running from a product workspace instead of the config repo, prefix `<config_dir>/` (`%USERPROFILE%\.gemini\config` on Windows, `~/.gemini/config` on POSIX) before `skills/app-debugger/scripts/run_diagnose.py`.

---

## 1. Pre-Run Verification One-Liners

```bash
# Verify system-diagnostics tool engine resolution
python skills/app-debugger/scripts/run_diagnose.py --probe

# Run app-debugger automated unit and eval tests
python -m unittest discover -s skills/app-debugger/tests -p "test_*.py"
```

---

## 2. Step-by-Step Diagnostic Recipes

1. **Tier 1 (Surface & Tests)**:
   ```bash
   python skills/app-debugger/scripts/run_diagnose.py surface --show-ids --show-routes
   python skills/app-debugger/scripts/run_diagnose.py tests
   # Targeted module runs (enforces 180s --timeout guard against exit/thread hangs):
   python skills/app-debugger/scripts/run_diagnose.py tests tests.test_mod1 tests.test_mod2
   ```
2. **Tier 2 (Container Runtime & Sync)**:
   ```bash
   python skills/app-debugger/scripts/run_diagnose.py container --lines 100 --sync-check <modified_files>
   ```
3. **Tier 3 (Browser UI Layout & Runtime Telemetry via CDP)**:
   ```bash
   # Live visible tab (brings tab to front, fails loud unless --allow-headless-fallback, captures console/HTTP/localStorage)
   python skills/app-debugger/scripts/run_diagnose.py ui --live --capture-runtime --audit-layout
   python skills/app-debugger/scripts/run_diagnose.py ui --live --wait 2.0 --audit-layout
   # Evaluate multi-statement JS without PowerShell quote stripping
   python skills/app-debugger/scripts/run_diagnose.py ui --live --capture-runtime --eval-file scratch/probe.js
   # Isolated headless background (fresh empty profile has no live localStorage/cookies)
   python skills/app-debugger/scripts/run_diagnose.py ui --headless --capture-runtime --audit-layout --screenshot scratch/bug_before.jpg
   ```
4. **Dynamic Domain Probes (Hardware, Databases, Network)**:
   ```bash
   python skills/app-debugger/scripts/run_diagnose.py probe list
   python skills/app-debugger/scripts/run_diagnose.py probe run camera_hardware
   python skills/app-debugger/scripts/run_diagnose.py probe new <name> --domain <domain>
   python skills/app-debugger/scripts/run_diagnose.py probe save <script> <name>
   ```
5. **Quarantined Tactical Defect Reproduction (Red-to-Green)**:
   ```bash
   python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001 --branch
   python -m unittest tests/quarantine/test_defect_001.py
   ```

---

## 3. Scenario Combinations Matrix

| Real-World Scenario / Objective | Mode / Inputs | Key Parameters | Exact Runnable Command |
| :--- | :--- | :--- | :--- |
| **Check Tool Engine Readiness** | Diagnostic probe | `--probe` | `python skills/app-debugger/scripts/run_diagnose.py --probe` |
| **Inspect Live Tab with Settle Delay (Scroll-Snap / Resting Offsets)** | Live visible tab | `--live --wait 2.0 --audit-layout` | `python skills/app-debugger/scripts/run_diagnose.py ui --live --wait 2.0 --audit-layout` |
| **Inspect Live Chrome Tab Bug** | Live visible tab | `--live --audit-layout` | `python skills/app-debugger/scripts/run_diagnose.py ui --live --audit-layout` |
| **Capture Pre-Fix Visual Proof** | Headless sandbox | `--screenshot` | `python skills/app-debugger/scripts/run_diagnose.py ui --screenshot scratch/bug_before.jpg` |
| **Audit Specific Failing Elements** | CSS selectors | `--selectors` | `python skills/app-debugger/scripts/run_diagnose.py ui --selectors "#player,.error-banner"` |
| **Inspect File Line Endings Before Edit** | Environment probe | Python one-liner | `python -c "print('CRLF' if b'\r\n' in open('file.py','rb').read() else 'LF')"` |
| **Diagnose Container Crash / CPU** | Docker service | `--lines --sync-check` | `python skills/app-debugger/scripts/run_diagnose.py container --lines 100 --sync-check app.py` |
| **Check AST Surface for Broken IDs** | Source repository | `--show-ids --show-routes` | `python skills/app-debugger/scripts/run_diagnose.py surface --show-ids --show-routes` |
| **Run Virtualenv Unit Test Suite** | Test runner | Auto-detects `.venv` | `python skills/app-debugger/scripts/run_diagnose.py tests` |
| **Full 3-Tier System Health Audit** | Dev server / repo | All tiers | `python skills/app-debugger/scripts/run_diagnose.py all` |
| **List Registered Domain Probes** | Probe registry | Discovers domain probes | `python skills/app-debugger/scripts/run_diagnose.py probe list` |
| **Probe Camera Hardware & Acquisition** | Video capture | Tests DirectShow/V4L2 & locks | `python skills/app-debugger/scripts/run_diagnose.py probe run camera_hardware` |
| **Scaffold Reusable Domain Probe** | Missing domain | Generates boilerplate probe | `python skills/app-debugger/scripts/run_diagnose.py probe new db_pool --domain database` |
| **Promote Scratch Script to Probe** | Verified scratch | Saves script to probe registry | `python skills/app-debugger/scripts/run_diagnose.py probe save scratch/probe.py db_pool` |
| **Unlock Quarantined Tactical Defect** | Quarantined defect | Failing Red repro in `tests/quarantine/` | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001` |
| **Unlock Defect & Checkout Micro-Branch** | Quarantined defect | Clean git branch + Red repro test | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001 --branch` |
| **Polyglot Latent Defect & Smell Scan** | Source repository | Py, JS/TS, CSS, Dart (SSOT) | `python skills/system-diagnostics/scripts/diagnose.py scan --path src/` |

---

## 4. Architecture & Dynamic Discovery

```
skills/app-debugger/
├── SKILL.md                          # 5-step workflow, Symptom Matrix & guardrails
├── references/
│   ├── command-matrix.md             # Full command matrix, pre-run probes & layout
│   └── environment-and-reporting.md  # Dev server safety, Windows hygiene & Dual Output
├── scripts/
│   └── run_diagnose.py               # Dynamic resolver & executor for system-diagnostics
├── evals/
│   └── evals.json                    # Realistic evaluation scenarios & expectations
└── tests/
    ├── __init__.py
    ├── test_run_diagnose.py          # Unit tests for dynamic resolver & fallbacks
    └── test_skill_evals.py           # Eval verification test suite
```
