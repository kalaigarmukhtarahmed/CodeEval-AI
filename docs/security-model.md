# Security model for uploaded repositories

CodeEval AI treats every uploaded repository as hostile. Phase 1 only stores and safely extracts a ZIP; it never runs repository code, installs dependencies, invokes project scripts, or exposes extracted content over the web.

## Upload controls

- Only filenames ending in `.zip` are accepted.
- Upload size is configurable through `MAX_UPLOAD_BYTES` (default: 25 MiB).
- Archive entries are capped by `MAX_ARCHIVE_FILES` (default: 5,000).
- Aggregate expanded size is capped by `MAX_UNCOMPRESSED_BYTES` (default: 100 MiB).
- ZIP integrity is checked with Python's archive validation.
- Absolute paths, `..` traversal, backslash paths, and symbolic links are rejected.
- Entries with an abnormal compression ratio are rejected using `MAX_COMPRESSION_RATIO` (default: 100:1).

## Storage and execution boundary

Archives and extracted workspaces are written beneath a server-only data directory. Their paths are persisted for backend use but are never returned by the public API. Each upload receives a unique UUID workspace. No uploaded file is executed in Phase 1.

## Future execution boundary

If later phases enable tests, they must use disposable, non-root isolated workers with no network, strict resource limits, no host mounts, and no secrets. Static analysis remains the default posture.
