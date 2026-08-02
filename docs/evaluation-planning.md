# Evaluation planning

Phase 2 creates a deterministic, versioned plan only. It does not execute Ruff, Bandit, Semgrep, ESLint, tests, dependency scans, performance benchmarks, or scoring.

Planner version `1.0` uses evidence-backed rules. Python plans static quality and security checks; JavaScript/TypeScript plans static quality; manifests plan dependency analysis; detected supported frameworks plan architecture analysis. Detected pytest, unittest, Jest, and Vitest create testing entries marked `sandbox_required` for a future isolated phase.

Every check stores an id, name, category, planned tool, reason, evidence, execution mode, and `planned` status. Categories are correctness, security, performance, testing, maintainability, and architecture. The same detection result and planner version always yield the same ordered plan.
