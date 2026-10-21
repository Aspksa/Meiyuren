# Infinity Growth v0.22 — bounded foundation

This module implements four requested directions as an **offline prototype**:

1. Neurogenesis: source-verified lexical topic clusters, bounded to 128 logical nodes.
2. Recursive brains: a parent-child tree up to four levels, with independent-source thresholds.
8. Curiosity: ranked evidence-gap questions, **not** autonomous Internet research.
10. Distributed Cortex: deterministic local shard plan (up to 32 partitions), **not** network federation.

## Guarantees and limitations

- Does not train an LLM, claim semantic generalization, or synthesize source content.
- Keeps scopes separate when generating topic groups.
- Requires at least three distinct evidence sources by default for topic growth.
- No network access, inter-device syncing, or externally published data.
- Resource caps are deliberate; infinite automatic growth would be unsafe.
- The index is currently an isolated computation module. Wiring it to the production memory-worker, privacy policy, storage persistence and UI requires additional reviewed changes.
- Performance and accuracy have not been measured on representative production workloads.

## Next integration gates

1. Convert only current, confirmed, source-backed and privacy-visible Memory Core records to Evidence.
2. Persist topic trees and deterministic partitions in a migration with audit and delete propagation.
3. Introduce configurable budgets and a dormant scheduled worker, opt-in by default.
4. Evaluate quality on independent holdout questions and benchmark memory/time before promotion.
5. Design secure authenticated remote nodes with encryption and explicit owner opt-in.
