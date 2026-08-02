# Findings model

Findings normalize tool JSON into category, tool, rule, severity, message, repository-relative location, evidence, and a SHA-256 fingerprint. Bandit HIGH/MEDIUM/LOW maps to high/medium/low. Ruff and ESLint rule violations map to low because they do not provide security severities. Absolute or outside-workspace paths are rejected.
