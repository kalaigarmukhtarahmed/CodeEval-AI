"""Controlled static analyzers. No project command, script, or config is executed."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

MAX_OUTPUT_BYTES = 1_000_000
TOOL_TIMEOUT_SECONDS = 30


def severity(tool: str, value: str | None, rule: str | None = None) -> str:
    value = (value or "").upper()
    if tool == "bandit":
        return {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}.get(value, "info")
    # Lint tools do not publish security severities; violations are deterministic low findings.
    return "low" if rule else "info"


def relative_path(workspace: str | Path, candidate: str | Path | None) -> str | None:
    """Return only a normalized path contained by the persisted workspace."""
    if not candidate:
        return None
    try:
        workspace_path = Path(workspace).resolve()
        path = Path(candidate)
        if not path.is_absolute():
            path = workspace_path / path
        return path.resolve().relative_to(workspace_path).as_posix()
    except (OSError, TypeError, ValueError):
        return None


def fingerprint(tool: str, rule: str | None, path: str | None, line: int | None, message: str) -> str:
    source = "|".join([tool, rule or "", path or "", str(line or ""), " ".join(message.split())])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@dataclass
class ToolResult:
    status: str
    output: str = ""
    error: str | None = None
    exit_code: int | None = None
    duration_ms: int = 0
    version: str | None = None


class StaticAnalyzerAdapter:
    tool = ""

    def is_available(self) -> bool:
        if shutil.which(self.tool):
            return True
        exe_dir = Path(sys.executable).parent
        if shutil.which(self.tool, path=str(exe_dir)):
            return True
        try:
            res = subprocess.run([sys.executable, "-m", self.tool, "--version"], capture_output=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def execute(self, workspace: str | Path) -> ToolResult:
        workspace = Path(workspace)
        if not self.is_available():
            return ToolResult("tool_unavailable", error=f"{self.tool} is not available")
        command = self.command(workspace)
        started = time.monotonic()
        try:
            completed = subprocess.run(command, cwd=workspace, shell=False, capture_output=True, text=True, timeout=TOOL_TIMEOUT_SECONDS)
            output = (completed.stdout or "")[:MAX_OUTPUT_BYTES]
            return ToolResult("completed", output, (completed.stderr or "")[:4000] or None, completed.returncode, int((time.monotonic() - started) * 1000))
        except subprocess.TimeoutExpired:
            return ToolResult("failed", error="analysis_timeout", duration_ms=int((time.monotonic() - started) * 1000))
        except OSError as error:
            return ToolResult("failed", error="analyzer_execution_error", duration_ms=int((time.monotonic() - started) * 1000))

    def command(self, workspace: Path) -> list[str]:
        raise NotImplementedError

    def parse(self, output: str, workspace: str | Path, check: dict) -> list[dict]:
        return []


class RuffAdapter(StaticAnalyzerAdapter):
    tool = "ruff"

    def command(self, workspace: Path) -> list[str]:
        if shutil.which(self.tool):
            return [self.tool, "check", "--output-format", "json", "--no-cache", str(workspace)]
        return [sys.executable, "-m", "ruff", "check", "--output-format", "json", "--no-cache", str(workspace)]

    def parse(self, output: str, workspace: str | Path, check: dict) -> list[dict]:
        try:
            rows = json.loads(output)
        except json.JSONDecodeError:
            return []
        return [self._finding(row, workspace, check) for row in rows if relative_path(workspace, row.get("filename"))]

    def _finding(self, row: dict, workspace: str | Path, check: dict) -> dict:
        path = relative_path(workspace, row.get("filename"))
        message = row.get("message", "Ruff finding")
        rule = row.get("code")
        return {
            "category": check["category"],
            "tool": "ruff",
            "rule_id": rule,
            "severity": severity("ruff", None, rule),
            "title": rule or "Ruff finding",
            "message": message,
            "file_path": path,
            "line_start": row.get("location", {}).get("row"),
            "line_end": row.get("end_location", {}).get("row"),
            "column_start": row.get("location", {}).get("column"),
            "column_end": row.get("end_location", {}).get("column"),
            "evidence": message,
            "recommendation": None,
            "fingerprint": fingerprint("ruff", rule, path, row.get("location", {}).get("row"), message)
        }


class BanditAdapter(StaticAnalyzerAdapter):
    tool = "bandit"

    def command(self, workspace: Path) -> list[str]:
        if shutil.which(self.tool):
            return [self.tool, "-r", str(workspace), "-f", "json"]
        return [sys.executable, "-m", "bandit", "-r", str(workspace), "-f", "json"]

    def parse(self, output: str, workspace: str | Path, check: dict) -> list[dict]:
        try:
            rows = json.loads(output).get("results", [])
        except json.JSONDecodeError:
            return []
        findings = []
        for row in rows:
            path = relative_path(workspace, row.get("filename"))
            if not path:
                continue
            message = row.get("issue_text", "Bandit finding")
            rule = row.get("test_id")
            findings.append({
                "category": check["category"],
                "tool": "bandit",
                "rule_id": rule,
                "severity": severity("bandit", row.get("issue_severity")),
                "title": row.get("test_name") or rule or "Bandit finding",
                "message": message,
                "file_path": path,
                "line_start": row.get("line_number"),
                "line_end": row.get("line_range", [None])[-1],
                "column_start": None,
                "column_end": None,
                "evidence": row.get("code") or message,
                "recommendation": None,
                "fingerprint": fingerprint("bandit", rule, path, row.get("line_number"), message)
            })
        return findings


class ESLintAdapter(StaticAnalyzerAdapter):
    tool = "eslint"

    def is_available(self) -> bool:
        return False  # Safe MVP: never load untrusted repository JS configuration/plugins.

    def command(self, workspace: Path) -> list[str]:
        return []

    def parse(self, output: str, workspace: str | Path, check: dict) -> list[dict]:
        try:
            rows = json.loads(output)
        except json.JSONDecodeError:
            return []
        findings = []
        for file in rows:
            path = relative_path(workspace, file.get("filePath"))
            if not path:
                continue
            for item in file.get("messages", []):
                message = item.get("message", "ESLint finding")
                rule = item.get("ruleId")
                findings.append({
                    "category": check["category"],
                    "tool": "eslint",
                    "rule_id": rule,
                    "severity": severity("eslint", None, rule),
                    "title": rule or "ESLint finding",
                    "message": message,
                    "file_path": path,
                    "line_start": item.get("line"),
                    "line_end": item.get("endLine"),
                    "column_start": item.get("column"),
                    "column_end": item.get("endColumn"),
                    "evidence": message,
                    "recommendation": None,
                    "fingerprint": fingerprint("eslint", rule, path, item.get("line"), message)
                })
        return findings


ADAPTERS = {
    "ruff": RuffAdapter(),
    "bandit": BanditAdapter(),
    "eslint": ESLintAdapter()
}
