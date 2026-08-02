# Project detection

Phase 2 statically inspects an already validated, private extraction workspace. It never executes, imports, builds, installs, or exposes uploaded repository content.

## Supported detection

- Languages: Python, JavaScript, TypeScript, HTML, CSS, and JSON.
- Python frameworks: FastAPI, Flask, Django.
- JavaScript/TypeScript frameworks: React, Next.js, Express, Vue, Vite.
- Package managers: pip, Poetry, npm, yarn, pnpm.
- Test frameworks: pytest, unittest, Jest, Vitest.

Framework and package-manager detections include structured file-and-reason evidence. A framework is reported only when a dependency, import, or recognized configuration file supports it.

## Source lines and percentages

Supported source files are read as UTF-8 and counted as nonblank, non-single-line-comment lines. Language percentages are each language's source-line share, rounded deterministically; any rounding remainder is assigned to the largest language so totals equal 100.

The detector skips `node_modules`, `.venv`, `venv`, `env`, `.git`, `dist`, `build`, `coverage`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.next`, and `out`. It also excludes recognized lockfiles and minified files from source statistics. These rules are centralized in `app/config.py`.

## Safety limits and limitations

Files above `MAX_INSPECT_FILE_BYTES` (1 MiB by default), binary files, symlinks, unreadable files, and ignored directories are skipped. Invalid UTF-8 is safely decoded with replacement rather than crashing analysis. This is static heuristic detection: it does not infer every custom framework, assess coverage, or execute tools.
