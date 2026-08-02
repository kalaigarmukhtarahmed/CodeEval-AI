"""Phase 9: Static Architecture Analyzer Service.

Analyzes repository structure, module separation, internal dependency graph,
circular internal dependencies, and architectural documentation WITHOUT executing uploaded code.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Any

from sqlalchemy.orm import Session

from ..models import AgentEvent, ArchitectureAnalysis, ArchitectureFinding
from .project_detector import ProjectDetector


@dataclass
class ArchitectureResult:
    __test__ = False
    status: str  # completed, failed, unsupported
    source_file_count: int = 0
    package_count: int = 0
    module_count: int = 0
    dependency_edge_count: int = 0
    circular_dependency_count: int = 0
    high_fan_out_count: int = 0
    largest_file_lines: int = 0
    average_file_lines: int = 0
    architecture_docs_present: bool = False
    score: int | None = None
    explanation: str | None = None
    findings: list[dict[str, Any]] | None = None

    def __post_init__(self):
        if self.findings is None:
            self.findings = []


def is_test_file(rel_path: str) -> bool:
    """Return True if path is considered a test file rather than source code."""
    p_lower = rel_path.lower()
    parts = p_lower.split("/")
    if any(part in ("tests", "test", "testing", "__tests__") for part in parts[:-1]):
        return True
    filename = parts[-1]
    return filename.startswith("test_") or filename.endswith("_test.py")


def path_to_module_name(rel_path: str) -> str:
    """Convert relative python path to dotted module notation (e.g. app/services/foo.py -> app.services.foo)."""
    p = rel_path.replace("\\", "/")
    if p.endswith(".py"):
        p = p[:-3]
    if p.endswith("/__init__"):
        p = p[:-9]
    return p.replace("/", ".").strip(".")


class ArchitectureAnalyzer:
    __test__ = False
    """Static architecture analyzer for Python repositories."""

    def analyze(self, db: Session, evaluation_id: str, snapshot_id: str, workspace_path: str | Path) -> ArchitectureAnalysis:
        workspace = Path(workspace_path).resolve()

        # Create AgentEvents
        db.add(AgentEvent(
            evaluation_id=evaluation_id,
            stage="ARCHITECTURE_ANALYSIS",
            status="started",
            message="Architecture analysis started",
            metadata_json={"workspace": str(workspace)}
        ))
        db.commit()

        # Check existing analysis
        existing = db.query(ArchitectureAnalysis).filter(
            ArchitectureAnalysis.evaluation_id == evaluation_id
        ).order_by(ArchitectureAnalysis.created_at.desc()).first()

        if existing:
            return existing

        res = self._analyze_workspace(workspace)

        analysis = ArchitectureAnalysis(
            evaluation_id=evaluation_id,
            snapshot_id=snapshot_id,
            status=res.status,
            source_file_count=res.source_file_count,
            package_count=res.package_count,
            module_count=res.module_count,
            dependency_edge_count=res.dependency_edge_count,
            circular_dependency_count=res.circular_dependency_count,
            high_fan_out_count=res.high_fan_out_count,
            largest_file_lines=res.largest_file_lines,
            average_file_lines=res.average_file_lines,
            architecture_docs_present=res.architecture_docs_present,
            score=res.score,
            explanation=res.explanation
        )
        db.add(analysis)
        db.flush()

        for f in res.findings:
            db.add(ArchitectureFinding(
                architecture_analysis_id=analysis.id,
                rule_id=f["rule_id"],
                severity=f["severity"],
                category=f.get("category", "architecture"),
                file_path=f["file_path"],
                message=f["message"],
                evidence=f.get("evidence")
            ))

        db.add(AgentEvent(
            evaluation_id=evaluation_id,
            stage="ARCHITECTURE_ANALYSIS",
            status="completed" if res.status == "completed" else "failed",
            message=f"Architecture analysis completed: Score {res.score if res.score is not None else 'N/A'}",
            metadata_json={
                "status": res.status,
                "score": res.score,
                "module_count": res.module_count,
                "circular_dependencies": res.circular_dependency_count
            }
        ))
        db.commit()
        return analysis

    def _analyze_workspace(self, workspace: Path) -> ArchitectureResult:
        ignored_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules", "data", "build", "dist", ".pytest_cache", ".coverage"}

        source_files: list[tuple[str, Path, int]] = []  # (rel_path, abs_path, line_count)
        packages: set[str] = set()

        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            rel_dir = os.path.relpath(root, workspace).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""

            has_py_files = False
            for f in files:
                if f.endswith(".py"):
                    has_py_files = True
                    abs_p = Path(root) / f
                    rel_p = (Path(rel_dir) / f).as_posix() if rel_dir else f

                    if not is_test_file(rel_p):
                        try:
                            lines = len(abs_p.read_text(encoding="utf-8", errors="ignore").splitlines())
                        except Exception:
                            lines = 0
                        source_files.append((rel_p, abs_p, lines))

            if has_py_files and rel_dir:
                packages.add(rel_dir)

        if not source_files:
            return ArchitectureResult(
                status="unsupported",
                explanation="No Python source files discovered for architecture analysis."
            )

        source_file_count = len(source_files)
        package_count = len(packages)
        module_count = source_file_count
        largest_file_lines = max(sf[2] for sf in source_files) if source_files else 0
        total_lines = sum(sf[2] for sf in source_files)
        average_file_lines = round(total_lines / source_file_count) if source_file_count > 0 else 0

        # Build module mapping
        # module_name -> rel_path
        module_map: dict[str, str] = {}
        for rel_p, _, _ in source_files:
            mod_name = path_to_module_name(rel_p)
            module_map[mod_name] = rel_p

        # AST Import Graph Construction
        # graph[src_mod] = set of target internal module names
        internal_graph: dict[str, set[str]] = {mod: set() for mod in module_map}

        for rel_p, abs_p, _ in source_files:
            src_mod = path_to_module_name(rel_p)
            try:
                content = abs_p.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content, filename=rel_p)
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target = alias.name
                        resolved = self._resolve_internal_module(target, src_mod, module_map)
                        if resolved and resolved != src_mod:
                            internal_graph[src_mod].add(resolved)
                elif isinstance(node, ast.ImportFrom):
                    mod_base = node.module or ""
                    level = node.level or 0
                    target_mod = self._resolve_relative_import(mod_base, level, src_mod)
                    resolved = self._resolve_internal_module(target_mod, src_mod, module_map)
                    if resolved and resolved != src_mod:
                        internal_graph[src_mod].add(resolved)

        # Compute graph metrics
        dependency_edge_count = sum(len(targets) for targets in internal_graph.values())
        fan_outs = {mod: len(targets) for mod, targets in internal_graph.items()}
        high_fan_out_modules = [mod for mod, fo in fan_outs.items() if fo > 8]
        high_fan_out_count = len(high_fan_out_modules)

        # Detect Circular Dependencies
        cycles = self._find_circular_dependencies(internal_graph)
        circular_dependency_count = len(cycles)

        # Documentation Presence Check
        architecture_docs_present = self._check_architecture_docs(workspace)

        # Evaluate Architecture Rules
        findings: list[dict[str, Any]] = []

        # ARCH001: Circular internal dependency
        for cycle in cycles:
            cycle_str = " -> ".join(cycle)
            first_mod = cycle[0]
            first_path = module_map.get(first_mod, first_mod)
            findings.append({
                "rule_id": "ARCH001",
                "severity": "high",
                "category": "architecture",
                "file_path": first_path,
                "message": f"Circular internal dependency detected: {cycle_str}",
                "evidence": f"Cycle path: {cycle_str}"
            })

        # ARCH002: Excessive module size (>500 lines for non-tiny projects)
        if source_file_count >= 3:
            for rel_p, _, lines in source_files:
                if lines > 500:
                    findings.append({
                        "rule_id": "ARCH002",
                        "severity": "medium",
                        "category": "architecture",
                        "file_path": rel_p,
                        "message": f"Excessive module size: {rel_p} contains {lines} lines (threshold: 500 lines)",
                        "evidence": f"File line count: {lines}"
                    })

        # ARCH003: High dependency fan-out (>8 internal modules)
        for mod in high_fan_out_modules:
            rel_p = module_map.get(mod, mod)
            fo = fan_outs[mod]
            findings.append({
                "rule_id": "ARCH003",
                "severity": "low",
                "category": "architecture",
                "file_path": rel_p,
                "message": f"High dependency fan-out: {mod} imports {fo} internal modules (threshold: 8)",
                "evidence": f"Fan-out count: {fo}"
            })

        # ARCH004: Excessive code concentration (>60% of total lines in 1 file for projects >=3 files and total >300)
        if source_file_count >= 3 and total_lines > 300:
            for rel_p, _, lines in source_files:
                ratio = lines / total_lines
                if ratio > 0.60:
                    findings.append({
                        "rule_id": "ARCH004",
                        "severity": "medium",
                        "category": "architecture",
                        "file_path": rel_p,
                        "message": f"Excessive code concentration: {rel_p} contains {round(ratio * 100)}% of total codebase lines",
                        "evidence": f"Lines: {lines} / Total: {total_lines} ({round(ratio * 100)}%)"
                    })

        # ARCH005: Mixed responsibilities (e.g., file has API routes AND database models AND business logic)
        for rel_p, abs_p, lines in source_files:
            if lines > 150:
                has_routes, has_models, has_logic = self._check_mixed_responsibilities(abs_p)
                if has_routes and has_models and has_logic:
                    findings.append({
                        "rule_id": "ARCH005",
                        "severity": "low",
                        "category": "architecture",
                        "file_path": rel_p,
                        "message": f"Mixed architectural responsibilities: {rel_p} combines API routing, database models, and application logic in a single file",
                        "evidence": "File contains API route decorators, ORM model definitions, and complex business functions."
                    })

        # ARCH006: Architecture documentation missing (Info only, no penalty)
        if not architecture_docs_present and source_file_count >= 3:
            findings.append({
                "rule_id": "ARCH006",
                "severity": "info",
                "category": "architecture",
                "file_path": "README.md",
                "message": "Architecture documentation unavailable (no dedicated architecture or project structure documentation discovered)",
                "evidence": "No README.md or ARCHITECTURE.md containing structural documentation found."
            })

        # Calculate Score
        # Base = 100. Deductions: Critical: -20, High: -12, Medium: -6, Low: -2, Info: 0
        deductions = 0
        seen_rules: set[tuple[str, str]] = set()
        for f in findings:
            key = (f["rule_id"], f["file_path"])
            if key in seen_rules:
                continue
            seen_rules.add(key)

            sev = f["severity"]
            if sev == "critical":
                deductions += 20
            elif sev == "high":
                deductions += 12
            elif sev == "medium":
                deductions += 6
            elif sev == "low":
                deductions += 2

        score_val = max(0, min(100, 100 - deductions))

        explanation = f"Modules: {module_count}, Packages: {package_count}, Dependency edges: {dependency_edge_count}, Circular dependencies: {circular_dependency_count}. Architecture findings: {len(findings)}. Penalty: -{deductions}. Final score: {score_val}."

        return ArchitectureResult(
            status="completed",
            source_file_count=source_file_count,
            package_count=package_count,
            module_count=module_count,
            dependency_edge_count=dependency_edge_count,
            circular_dependency_count=circular_dependency_count,
            high_fan_out_count=high_fan_out_count,
            largest_file_lines=largest_file_lines,
            average_file_lines=average_file_lines,
            architecture_docs_present=architecture_docs_present,
            score=score_val,
            explanation=explanation,
            findings=findings
        )

    def _resolve_relative_import(self, mod_base: str, level: int, src_mod: str) -> str:
        if level == 0:
            return mod_base
        parts = src_mod.split(".")
        if level <= len(parts):
            base_parts = parts[:-level]
            if mod_base:
                base_parts.append(mod_base)
            return ".".join(base_parts)
        return mod_base

    def _resolve_internal_module(self, target_name: str, src_mod: str, module_map: dict[str, str]) -> str | None:
        if not target_name:
            return None

        if target_name in module_map:
            return target_name

        # Try prefix matching (e.g. target_name = "services.user_service" or "services")
        for mod in module_map:
            if mod == target_name or mod.startswith(target_name + ".") or target_name.startswith(mod + "."):
                return mod
            # Also check relative to package parent
            src_parts = src_mod.split(".")
            if len(src_parts) > 1:
                pkg_parent = ".".join(src_parts[:-1])
                combined = f"{pkg_parent}.{target_name}"
                if combined in module_map:
                    return combined

        return None

    def _find_circular_dependencies(self, graph: dict[str, set[str]]) -> list[list[str]]:
        """Find simple cycles in directed internal import graph."""
        cycles: list[list[str]] = []
        visited_cycles: set[tuple[str, ...]] = set()

        nodes = list(graph.keys())

        def dfs(curr: str, path: list[str], visited: set[str]):
            for nxt in graph.get(curr, []):
                if nxt in path:
                    idx = path.index(nxt)
                    cycle = path[idx:] + [nxt]
                    # Normalize cycle
                    min_idx = cycle[:-1].index(min(cycle[:-1]))
                    norm = tuple(cycle[min_idx:-1] + cycle[:min_idx] + [cycle[min_idx]])
                    if norm not in visited_cycles:
                        visited_cycles.add(norm)
                        cycles.append(list(norm))
                elif nxt not in visited:
                    visited.add(nxt)
                    dfs(nxt, path + [nxt], visited)
                    visited.remove(nxt)

        for start_node in nodes:
            dfs(start_node, [start_node], {start_node})

        return cycles

    def _check_architecture_docs(self, workspace: Path) -> bool:
        doc_candidates = ["README.md", "ARCHITECTURE.md", "CONTRIBUTING.md", "docs/architecture.md", "docs/index.md", "docs/README.md"]
        keywords = ["architecture", "project structure", "component", "module responsibility", "system design"]

        for cand in doc_candidates:
            p = workspace / cand
            if p.exists() and p.is_file():
                try:
                    txt = p.read_text(encoding="utf-8", errors="ignore").lower()
                    if any(kw in txt for kw in keywords):
                        return True
                except Exception:
                    pass
        return False

    def _check_mixed_responsibilities(self, file_path: Path) -> tuple[bool, bool, bool]:
        """Check if file contains route handlers, DB models, and complex logic."""
        try:
            txt = file_path.read_text(encoding="utf-8", errors="ignore")
            has_routes = any(w in txt for w in ("@app.get", "@app.post", "@router.", "@blueprint.", "APIRouter(", "FastAPI("))
            has_models = any(w in txt for w in ("Base)", "mapped_column(", "db.Column(", "models.Model", "Schema("))
            has_logic = any(w in txt for w in ("def process_", "def calculate_", "def verify_", "def execute_"))
            return has_routes, has_models, has_logic
        except Exception:
            return False, False, False
