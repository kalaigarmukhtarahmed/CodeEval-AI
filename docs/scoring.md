# Scoring 1.0

Only executed-evidence categories are measured. Security starts at 100 and subtracts critical 25, high 15, medium 8, low 3, info 1 for normalized Bandit findings. Maintainability starts at 100 and subtracts critical 10, high 6, medium 4, low 2, info 1 for Ruff findings. Scores clamp to 0–100. Correctness, performance, testing, and architecture are `not_measured` with `score: null`.

Overall is the rounded equal average of measured category scores only. Assessment coverage reports measured categories out of six; unmeasured categories are never treated as zero.
