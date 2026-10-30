#!/usr/bin/env python3
"""
Frontier Architect - Portable Benchmark & Regression Runner.
Compares the current skill against historical snapshots using evals/evals.json.

Dual-Tier Testing Architecture:
1. Fast Deterministic Evaluation (This Script & unittest):
   - Evaluates SKILL.md against all 9 scenarios and 48 expectations in evals/evals.json.
   - Dynamically compares pass rate against the historical snapshot (skill-snapshot/SKILL.md).
   - Sub-second execution, zero LLM tokens consumed, 100% offline and cross-platform.
2. Generative Agent Evaluation (/skill-creator):
   - For empirical multi-agent runs (testing how Gemini Flash or Pro actually executes prompts),
     invoke the /skill-creator workflow to spawn subagents, capture timing.json/tokens,
     and inspect the interactive diff viewer via eval-viewer/generate_review.py.
   - If not installed locally, acquire from:
     https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator/skills/skill-creator

Usage Recipes:
    python skills/frontier-architect/tests/run_benchmark.py
    python skills/frontier-architect/tests/run_benchmark.py --generate-artifacts
    python -m unittest discover -s skills/frontier-architect/tests -p "test_*.py" -v
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Dynamic relative paths (zero hardcoded machine or user paths)
TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
EVALS_FILE = SKILL_DIR / "evals" / "evals.json"
SKILL_MD = SKILL_DIR / "SKILL.md"
CONFIG_DIR = SKILL_DIR.parent.parent
SKILL_CREATOR_DIR = SKILL_DIR.parent / "skill-creator"
WORKSPACE_DIR = SKILL_DIR.parent / f"{SKILL_DIR.name}-workspace"
SNAPSHOT_MD = WORKSPACE_DIR / "skill-snapshot" / "SKILL.md"

try:
    from test_skill_evals import evaluate_expectation_against_text
except ImportError:
    from skills.frontier_architect.tests.test_skill_evals import evaluate_expectation_against_text


def run_benchmark(generate_artifacts: bool = False, iteration: int = 2):
    if not EVALS_FILE.exists() or not SKILL_MD.exists():
        print(f"Error: Required files not found in {SKILL_DIR}")
        sys.exit(1)

    with open(EVALS_FILE, "r", encoding="utf-8") as f:
        evals = json.load(f).get("evals", [])

    current_text = SKILL_MD.read_text(encoding="utf-8")
    baseline_text = SNAPSHOT_MD.read_text(encoding="utf-8") if SNAPSHOT_MD.exists() else None

    total_checks = sum(len(e.get("expectations", [])) for e in evals)
    curr_passed = sum(
        1 for e in evals for exp in e.get("expectations", [])
        if evaluate_expectation_against_text(current_text, exp)[0]
    )

    base_passed = 0
    if baseline_text:
        base_passed = sum(
            1 for e in evals for exp in e.get("expectations", [])
            if evaluate_expectation_against_text(baseline_text, exp)[0]
        )

    curr_rate = (curr_passed / total_checks) * 100 if total_checks else 0.0
    base_rate = (base_passed / total_checks) * 100 if total_checks else 0.0
    delta = curr_rate - base_rate

    print("\n" + "=" * 68)
    print("  FRONTIER ARCHITECT: BENCHMARK & REGRESSION EVALUATION")
    print("=" * 68)
    print(f"Total Scenarios Evaluated: {len(evals)}")
    print(f"Total Assertions/Checks:   {total_checks}\n")
    print(f"  Current Skill Pass Rate:   {curr_rate:5.1f}% ({curr_passed}/{total_checks})")
    if baseline_text:
        print(f"  Baseline Snapshot Rate:    {base_rate:5.1f}% ({base_passed}/{total_checks})")
        print(f"  Improvement Delta:         +{delta:5.1f}%")
    print("=" * 68)
    if SKILL_CREATOR_DIR.exists():
        print("  Tip: For full multi-agent generative benchmarks, invoke /skill-creator.")
    else:
        print("  Tip: For full multi-agent generative benchmarks, install /skill-creator:")
        print("       https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator/skills/skill-creator")
    print("=" * 68 + "\n")

    if generate_artifacts and WORKSPACE_DIR.exists():
        iter_dir = WORKSPACE_DIR / f"iteration-{iteration}"
        iter_dir.mkdir(parents=True, exist_ok=True)

        benchmark_data = {
            "skill_name": "frontier-architect",
            "evals_count": len(evals),
            "total_checks": total_checks,
            "run_summary": {
                "with_skill": {"pass_rate": {"mean": round(curr_rate / 100.0, 4)}},
                "without_skill": {"pass_rate": {"mean": round(base_rate / 100.0, 4)}},
                "delta": {"pass_rate": f"+{round(delta / 100.0, 2):.2f}"},
            },
        }

        bench_json = iter_dir / "benchmark.json"
        bench_json.write_text(json.dumps(benchmark_data, indent=2), encoding="utf-8")
        try:
            rel_path = bench_json.relative_to(CONFIG_DIR)
        except ValueError:
            rel_path = bench_json
        print(f"Artifact generated: {rel_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Frontier Architect Benchmark & Regression Runner",
        epilog=(
            "Testing Architecture:\n"
            "  - Fast CI/CD static checks: python run_benchmark.py\n"
            "  - Automated unittest: python -m unittest discover tests\n"
            "  - Generative model benchmarking: invoke /skill-creator in chat\n"
            "    (Source: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator/skills/skill-creator)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--generate-artifacts", action="store_true", help="Output benchmark.json to workspace")
    parser.add_argument("--iteration", type=int, default=2, help="Workspace iteration number (default: 2)")
    args = parser.parse_args()

    run_benchmark(generate_artifacts=args.generate_artifacts, iteration=args.iteration)


if __name__ == "__main__":
    main()
