from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("CODEEVAL_DATA_DIR", BASE_DIR / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
WORKSPACE_DIR = DATA_DIR / "workspaces"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'codeeval.db'}")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_ARCHIVE_FILES = int(os.getenv("MAX_ARCHIVE_FILES", "5000"))
MAX_UNCOMPRESSED_BYTES = int(os.getenv("MAX_UNCOMPRESSED_BYTES", str(100 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = float(os.getenv("MAX_COMPRESSION_RATIO", "100"))
MAX_INSPECT_FILE_BYTES = int(os.getenv("MAX_INSPECT_FILE_BYTES", str(1024 * 1024)))

# Phase 8 Controlled Test Execution Settings
ENABLE_LOCAL_TEST_EXECUTION = os.getenv("CODEEVAL_ENABLE_LOCAL_TEST_EXECUTION", "false").lower() in ("true", "1", "yes")
TEST_TIMEOUT_SECONDS = int(os.getenv("TEST_TIMEOUT_SECONDS", "30"))
MAX_TEST_FILES = int(os.getenv("MAX_TEST_FILES", "500"))
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_BYTES", str(100 * 1024)))

# Phase 10 Performance Benchmark Settings
ENABLE_BENCHMARKS = os.getenv("CODEEVAL_ENABLE_BENCHMARKS", "false").lower() in ("true", "1", "yes")


# Centralized exclusion policy for untrusted repository inspection.
IGNORED_DIRECTORY_NAMES = frozenset({
    "node_modules", ".venv", "venv", "env", ".git", "dist", "build", "coverage",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".next", "out",
})
GENERATED_FILE_NAMES = frozenset({"package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"})
