# Meiyuren Cognitive Evolution Lab (experimental v0.16)

This is an **opt-in, offline** foundation for evidence-based evolution of the existing eight logical memory domains. It is **not** eight independent trained LLMs, live web research, autonomous coding, or an unattended software deployment pipeline.

## Available now

- Eight stable logical memory domains, provenance-bearing research/evidence records, locally isolated from Cloud.ru by default.
- Deterministic topical specializations from repeated evidence titles (a suggested microbrain index, not training).
- Three candidate retrieval strategies evaluated against **user/importer supplied** labeled cases.
- Separated training and holdout fixture partitions. Automatic promotion requires at least three training cases, five holdout cases, and a strict improvement over the current strategy on holdout. This is a local experimental gate, not proof of general intelligence.
- Recorded proposals for code, research and model changes: only stored as pending. No source mutation, shell execution, downloading, self-installation or deployment.
- SQLite WAL, bounded evidence and fixture tables, stable content-addressed identifiers.

## Usage

Run from repository root with Python 3.11+:

```sh
python -m backend.app.cognitive_evolution status
python -m backend.app.cognitive_evolution import-evidence --json '{"brain":"knowledge","title":"Python retrieval","content":"Observed from a local verified experiment","source_uri":"local:experiment/1","observed_at":"2026-10-21T00:00:00+00:00","trust":"source_checked"}'
python -m backend.app.cognitive_evolution evolve
python -m pytest backend/tests/test_cognitive_evolution.py -q
```

Data is stored at `data/cognitive_evolution.sqlite3`, independently of the primary Memory Core database. This prevents accidental migration of user facts and permits experimental rollback by backing up or removing **only this separate file while the app is stopped**.

Import labeled fixture examples using `add-fixture --json '{"query":"...","expected_id":"...","split":"train"}'` (or `holdout`). Use trusted, independently checked holdout labels, not queries synthesized from target facts. A failed or underpowered experiment preserves the active strategy.

## Next integration gates

1. Integrate the lab into normal Memory Core operation only after realistic long-dialog benchmarks, a robust privacy review, and a migration plan.
2. Plug in an opt-in per-brain provider/model registry with explicit credential and cost policy; no hidden cloud traffic.
3. Add allowlisted external research collectors that preserve sources and distinguish verified vs. unverified content.
4. Build patch candidates in disposable worktrees with enforced test suites and explicit deployment authorization. Never execute arbitrary AI-generated code inside the user's primary runtime.
5. Add human-reviewed independent evaluations to avoid overfitting to self-generated fixtures.

**Security:** `source_uri` is provenance metadata, not a URL automatically fetched by the application. Imported text remains untrusted. The lab does not bypass the existing chat authorization or Cloud.ru consent mechanisms.
