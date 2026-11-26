# Child Plan: Remote Pull & Conformance

Parent: `universal_debug_observation_connector_plan`, Milestone 4. Specification: parent **CLI Contract** (`pull`), **Conformance Contract**, **Wire Contract v1**, decisions D11, D12, D14.

**Pre-Flight:** invariants = pull is atomic (all fetches finish before the single `save_catalog`; any failure writes nothing); non-loopback refused (exit 2) unless `--allow-remote` (then warns); no redirects followed (a redirect could leave loopback); stdlib `urllib` only; local triage fields survive a merge; verify never stores data (`dry_run=1` only). Flow = CLI -> `observation_pull` -> `observation_merge` -> `observation_store` primitives. Edge cases = unreachable, contract version mismatch, `enabled` false, truncated list, malformed JSON, oversize response, remote entry with forbidden keys. Verifier = command below.

**Decision:** `pull --status` defaults to `all` (not `active`) so remote resolutions sync; the contract left the default open.

## Milestone 4

- [x] **system-diagnostics/scripts/observation_merge.py**: merge one remote entry into a catalog (new / updated / unchanged).
- [x] **system-diagnostics/scripts/observation_pull.py**: loopback preflight, health check, fetch, merge, one atomic save.
- [x] **system-diagnostics/scripts/observation_verify.py**: conformance checks, `PASS`/`FAIL`/`SKIP`.
- [x] **system-diagnostics/scripts/observation_cli_remote.py**: `pull` and `verify-connector` flags and handlers; one-line hooks in `observation_cli.py`.
- [x] **system-diagnostics/tests/**: `test_observation_merge.py`, `test_observation_pull.py`, `test_observation_verify.py` (stub servers on `127.0.0.1`, ephemeral ports).

**Verifier**: `python3 -m unittest discover -s system-diagnostics/tests -p "test_observation_*.py"`
