# Static evaluation

Phase 3 consumes the persisted Phase 2 plan and runs only CodeEval-controlled Ruff and Bandit commands with argument arrays, no shell, a timeout, and bounded output. ESLint is deliberately skipped in this MVP because loading repository configuration or plugins could execute untrusted JavaScript. Unavailable tools are recorded as `tool_unavailable`.

Runs clear prior findings/check records for the same evaluation, then recreate them deterministically. This prevents duplicate findings. Phase 3 records evidence and counts only; it creates no scores.
