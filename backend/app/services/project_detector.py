"""Read-only, deterministic inspection of untrusted uploaded repositories."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import tomllib

from ..config import GENERATED_FILE_NAMES, IGNORED_DIRECTORY_NAMES, MAX_INSPECT_FILE_BYTES

LANGUAGE_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".json": "JSON",
}
TEST_FILE_PATTERN = re.compile(r"(^test_.*\.py$|.*_test\.py$|.*\.(test|spec)\.(js|jsx|ts|tsx)$)", re.IGNORECASE)
MANIFEST_NAMES = {"requirements.txt", "pyproject.toml", "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}
CONFIG_NAMES = {"pytest.ini", "setup.cfg", "jest.config.js", "jest.config.cjs", "jest.config.mjs", "vitest.config.js", "vitest.config.ts", "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs"}


@dataclass
class FileRecord:
    relative_path: str
    path: Path
    suffix: str
    text: str | None


@dataclass
class DetectionResult:
    total_source_files: int
    total_source_lines: int
    test_file_count: int
    languages: dict[str, int]
    language_lines: dict[str, int]
    language_evidence: dict[str, list[str]]
    frameworks: list[dict]
    package_managers: list[dict]
    test_frameworks: list[dict]
    test_directories: list[str]
    manifest_files: list[str]
    source_directories: list[str]
    configuration_files: list[str]


def _evidence(name: str, file: str, reason: str) -> dict:
    return {"name": name, "evidence": [{"file": file, "reason": reason}]}


def _dedupe_detections(items: list[dict]) -> list[dict]:
    combined: dict[str, list[dict]] = {}
    for item in items:
        combined.setdefault(item["name"], []).extend(item["evidence"])
    return [{"name": name, "evidence": evidence} for name, evidence in sorted(combined.items())]


class ProjectDetector:
    """Walks only the already-safe extraction workspace; it never executes content."""

    def inspect(self, workspace_path: str | Path) -> DetectionResult:
        workspace = Path(workspace_path)
        records: list[FileRecord] = []
        for root, directory_names, file_names in os.walk(workspace, topdown=True, followlinks=False):
            root_path = Path(root)
            directory_names[:] = sorted(
                name for name in directory_names
                if name not in IGNORED_DIRECTORY_NAMES and not (root_path / name).is_symlink()
            )
            for filename in sorted(file_names):
                path = root_path / filename
                if path.is_symlink():
                    continue
                try:
                    if not path.is_file() or path.stat().st_size > MAX_INSPECT_FILE_BYTES:
                        continue
                    raw = path.read_bytes()
                except OSError:
                    continue
                if b"\x00" in raw:
                    continue
                relative_path = path.relative_to(workspace).as_posix()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("utf-8", errors="replace")
                records.append(FileRecord(relative_path, path, path.suffix.lower(), text))
        return self._build_result(records)

    def _build_result(self, records: list[FileRecord]) -> DetectionResult:
        language_lines: dict[str, int] = defaultdict(int)
        language_files: dict[str, list[str]] = defaultdict(list)
        test_files = []
        manifest_files, configuration_files = [], []
        test_dirs: set[str] = set()
        for record in records:
            name = Path(record.relative_path).name
            if name in MANIFEST_NAMES:
                manifest_files.append(record.relative_path)
            if name in CONFIG_NAMES or ".config." in name:
                configuration_files.append(record.relative_path)
            if TEST_FILE_PATTERN.match(name):
                test_files.append(record.relative_path)
            for parent in Path(record.relative_path).parents:
                if parent.name.lower() in {"test", "tests", "__tests__"}:
                    test_dirs.add(parent.as_posix())
            language = LANGUAGE_EXTENSIONS.get(record.suffix)
            if language and name not in GENERATED_FILE_NAMES and not name.endswith((".min.js", ".min.css")):
                lines = self._source_lines(record.text or "", language)
                language_lines[language] += lines
                language_files[language].append(record.relative_path)
        total_lines = sum(language_lines.values())
        languages = {
            language: round((line_count / total_lines) * 100) if total_lines else 0
            for language, line_count in sorted(language_lines.items())
        }
        # Correct rounding deterministically so percentages total 100 when code exists.
        if languages and total_lines:
            largest = sorted(language_lines, key=lambda item: (-language_lines[item], item))[0]
            languages[largest] += 100 - sum(languages.values())
        return DetectionResult(
            total_source_files=sum(len(files) for files in language_files.values()), total_source_lines=total_lines,
            test_file_count=len(test_files), languages=languages, language_lines=dict(sorted(language_lines.items())),
            language_evidence={name: paths[:20] for name, paths in sorted(language_files.items())},
            frameworks=self._frameworks(records), package_managers=self._package_managers(records),
            test_frameworks=self._test_frameworks(records), test_directories=sorted(test_dirs),
            manifest_files=sorted(manifest_files), source_directories=self._source_directories(records),
            configuration_files=sorted(configuration_files),
        )

    @staticmethod
    def _source_lines(text: str, language: str) -> int:
        prefixes = {"Python": ("#",), "JavaScript": ("//",), "TypeScript": ("//",), "CSS": ("/*",), "HTML": ("<!--",), "JSON": ()}
        return sum(1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith(prefixes[language]))

    @staticmethod
    def _source_directories(records: list[FileRecord]) -> list[str]:
        known = {"src", "app", "backend", "frontend", "lib", "server", "client"}
        found = {parent.as_posix() for record in records for parent in Path(record.relative_path).parents if parent.name in known}
        return sorted(found)

    @staticmethod
    def _package_json(records: list[FileRecord]) -> list[tuple[FileRecord, dict]]:
        parsed = []
        for record in records:
            if Path(record.relative_path).name == "package.json":
                try:
                    parsed.append((record, json.loads(record.text or "{}")))
                except (json.JSONDecodeError, TypeError):
                    pass
        return parsed

    @staticmethod
    def _pyproject(records: list[FileRecord]) -> list[tuple[FileRecord, dict]]:
        parsed = []
        for record in records:
            if Path(record.relative_path).name == "pyproject.toml":
                try:
                    parsed.append((record, tomllib.loads(record.text or "")))
                except (tomllib.TOMLDecodeError, TypeError):
                    pass
        return parsed

    def _frameworks(self, records: list[FileRecord]) -> list[dict]:
        found: list[dict] = []
        requirements = [(record, (record.text or "").lower()) for record in records if Path(record.relative_path).name == "requirements.txt"]
        for framework, dependency in (("FastAPI", "fastapi"), ("Flask", "flask"), ("Django", "django")):
            for record, text in requirements:
                if re.search(rf"(?m)^\s*{dependency}(?:[\[<>=!~;\s]|$)", text):
                    found.append(_evidence(framework, record.relative_path, f"dependency {dependency} detected"))
        for record, data in self._pyproject(records):
            serialized = json.dumps(data).lower()
            for framework, dependency in (("FastAPI", "fastapi"), ("Flask", "flask"), ("Django", "django")):
                if f'"{dependency}' in serialized:
                    found.append(_evidence(framework, record.relative_path, f"dependency {dependency} detected"))
        for record in records:
            if record.suffix == ".py":
                for framework, module in (("FastAPI", "fastapi"), ("Flask", "flask"), ("Django", "django")):
                    if re.search(rf"(?m)^\s*(from|import)\s+{module}(?:\.|\s|$)", record.text or ""):
                        found.append(_evidence(framework, record.relative_path, f"import {module} detected"))
        for record, data in self._package_json(records):
            dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for framework, dependency in (("React", "react"), ("Next.js", "next"), ("Express", "express"), ("Vue", "vue"), ("Vite", "vite")):
                if dependency in dependencies:
                    found.append(_evidence(framework, record.relative_path, f"dependency {dependency} detected"))
        config_map = {"vite.config": "Vite", "next.config": "Next.js"}
        for record in records:
            for prefix, framework in config_map.items():
                if Path(record.relative_path).name.startswith(prefix):
                    found.append(_evidence(framework, record.relative_path, f"{prefix} configuration detected"))
        return _dedupe_detections(found)

    def _package_managers(self, records: list[FileRecord]) -> list[dict]:
        found: list[dict] = []
        names = {Path(record.relative_path).name: record for record in records}
        if "requirements.txt" in names:
            found.append(_evidence("pip", names["requirements.txt"].relative_path, "requirements.txt detected"))
        for record, data in self._pyproject(records):
            if "poetry" in data.get("tool", {}):
                found.append(_evidence("Poetry", record.relative_path, "[tool.poetry] detected"))
            elif "project" in data:
                found.append(_evidence("pip", record.relative_path, "[project] metadata detected"))
        if "poetry.lock" in names:
            found.append(_evidence("Poetry", names["poetry.lock"].relative_path, "poetry.lock detected"))
        locks = (("npm", "package-lock.json"), ("npm", "npm-shrinkwrap.json"), ("yarn", "yarn.lock"), ("pnpm", "pnpm-lock.yaml"))
        for manager, filename in locks:
            if filename in names:
                found.append(_evidence(manager, names[filename].relative_path, f"{filename} detected"))
        if "package.json" in names and not any(filename in names for _, filename in locks):
            found.append(_evidence("npm", names["package.json"].relative_path, "package.json detected without another lockfile"))
        return _dedupe_detections(found)

    def _test_frameworks(self, records: list[FileRecord]) -> list[dict]:
        found: list[dict] = []
        for record in records:
            name, text = Path(record.relative_path).name, record.text or ""
            if name in {"pytest.ini", "conftest.py"} or (record.suffix == ".py" and re.search(r"(?m)^\s*(from|import)\s+pytest", text)):
                found.append(_evidence("pytest", record.relative_path, f"{name} or pytest import detected"))
            if record.suffix == ".py" and re.search(r"(?m)^\s*(from|import)\s+unittest", text):
                found.append(_evidence("unittest", record.relative_path, "unittest import detected"))
            if name.startswith("jest.config"):
                found.append(_evidence("Jest", record.relative_path, "Jest configuration detected"))
            if name.startswith("vitest.config"):
                found.append(_evidence("Vitest", record.relative_path, "Vitest configuration detected"))
        for record, data in self._package_json(records):
            dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for framework, dependency in (("Jest", "jest"), ("Vitest", "vitest")):
                if dependency in dependencies:
                    found.append(_evidence(framework, record.relative_path, f"dependency {dependency} detected"))
        for record, data in self._pyproject(records):
            if "pytest" in json.dumps(data).lower():
                found.append(_evidence("pytest", record.relative_path, "pytest configuration or dependency detected"))
        return _dedupe_detections(found)
