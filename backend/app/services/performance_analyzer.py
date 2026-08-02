"""Phase 10: Performance Analyzer Service.

Static AST inspection of Python repositories for performance anti-patterns,
loop inefficiencies, database queries in loops, file operations in loops,
blocking operations, large functions, high complexity, and duplicate computations.
NEVER executes or imports untrusted repository code unless benchmark execution
is explicitly enabled in trusted local development configuration.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any

from sqlalchemy.orm import Session

from .. import config
from ..models import AgentEvent, PerformanceAnalysis, PerformanceFinding
from .architecture_analyzer import is_test_file


@dataclass
class PerformanceResult:
    __test__ = False
    status: str  # completed, failed, unsupported
    score: int | None = 100
    functions: int = 0
    loops: int = 0
    nested_loops: int = 0
    average_complexity: int = 0
    benchmark_enabled: bool = False
    benchmark_time_ms: int | None = None
    findings: list[dict[str, Any]] | None = None

    def __post_init__(self):
        if self.findings is None:
            self.findings = []


def calculate_complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Calculate cyclomatic complexity of a function node."""
    complexity = 1
    for child in ast.walk(node):
        if child is node:
            continue
        # Skip nested function definitions to avoid double counting
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(child, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Assert)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(1, len(child.values) - 1)
        elif isinstance(child, ast.comprehension):
            complexity += 1 + len(child.ifs)
    return complexity


def is_route_or_view(func_node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str) -> bool:
    """Determine whether a function is a route handler or web view."""
    file_lower = file_path.lower()
    if any(k in file_lower for k in ("views.py", "routes.py", "endpoints.py", "api.py", "app.py", "main.py")):
        return True

    # Check parameter names (e.g. request)
    arg_names = [arg.arg.lower() for arg in func_node.args.args]
    if "request" in arg_names or "req" in arg_names:
        return True

    # Check decorator names
    for dec in func_node.decorator_list:
        dec_str = ""
        if isinstance(dec, ast.Name):
            dec_str = dec.id.lower()
        elif isinstance(dec, ast.Attribute):
            dec_str = dec.attr.lower()
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                dec_str = dec.func.id.lower()
            elif isinstance(dec.func, ast.Attribute):
                dec_str = dec.func.attr.lower()

        if any(w in dec_str for w in ("route", "get", "post", "put", "delete", "patch", "api_view", "view")):
            return True

    return False


class PerformanceAnalyzer:
    __test__ = False
    """Static Performance Analyzer for Python Repositories."""

    def analyze(
        self, db: Session, evaluation_id: str, snapshot_id: str, workspace_path: str | Path
    ) -> PerformanceAnalysis:
        workspace = Path(workspace_path).resolve()

        db.add(
            AgentEvent(
                evaluation_id=evaluation_id,
                stage="PERFORMANCE_ANALYSIS",
                status="started",
                message="Performance analysis started",
                metadata_json={"workspace": str(workspace)},
            )
        )
        db.commit()

        existing = (
            db.query(PerformanceAnalysis)
            .filter(PerformanceAnalysis.evaluation_id == evaluation_id)
            .order_by(PerformanceAnalysis.created_at.desc())
            .first()
        )
        if existing:
            return existing

        res = self._analyze_workspace(workspace)

        analysis = PerformanceAnalysis(
            evaluation_id=evaluation_id,
            snapshot_id=snapshot_id,
            score=res.score,
            functions=res.functions,
            loops=res.loops,
            nested_loops=res.nested_loops,
            average_complexity=res.average_complexity,
            benchmark_enabled=res.benchmark_enabled,
            benchmark_time_ms=res.benchmark_time_ms,
        )
        db.add(analysis)
        db.flush()

        finding_objs = []
        for f in res.findings:
            finding_objs.append(
                PerformanceFinding(
                    analysis_id=analysis.id,
                    rule=f["rule"],
                    severity=f["severity"],
                    file_path=f["file_path"],
                    line=f.get("line"),
                    message=f["message"],
                    penalty=f["penalty"],
                )
            )
        db.add_all(finding_objs)
        db.commit()

        db.add(
            AgentEvent(
                evaluation_id=evaluation_id,
                stage="PERFORMANCE_ANALYSIS",
                status="completed",
                message="Performance analysis completed",
                metadata_json={"score": res.score, "finding_count": len(res.findings)},
            )
        )
        db.add(
            AgentEvent(
                evaluation_id=evaluation_id,
                stage="PERFORMANCE_ANALYSIS",
                status="completed",
                message="Performance score generated",
                metadata_json={"score": res.score},
            )
        )
        db.commit()

        return analysis

    def _analyze_workspace(self, workspace: Path) -> PerformanceResult:
        python_files: list[tuple[Path, str]] = []
        total_lines = 0

        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in config.IGNORED_DIRECTORY_NAMES]
            for file in files:
                if file.endswith(".py"):
                    full_p = Path(root) / file
                    try:
                        rel_p = str(full_p.relative_to(workspace)).replace("\\", "/")
                    except ValueError:
                        rel_p = file
                    if not is_test_file(rel_p):
                        python_files.append((full_p, rel_p))

        for full_p, _ in python_files:
            try:
                total_lines += len(full_p.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                pass

        is_small_repo = (len(python_files) < 3) or (total_lines < 150)

        total_functions = 0
        total_loops = 0
        nested_loops_count = 0
        complexities: list[int] = []
        findings: list[dict[str, Any]] = []

        t_start = time.perf_counter()

        for full_p, rel_p in python_files:
            try:
                content = full_p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content, filename=rel_p)
            except SyntaxError:
                continue

            file_findings, f_count, l_count, nl_count, f_complexities = self._analyze_ast(
                tree, rel_p, is_small_repo
            )
            findings.extend(file_findings)
            total_functions += f_count
            total_loops += l_count
            nested_loops_count += nl_count
            complexities.extend(f_complexities)

        t_end = time.perf_counter()

        benchmark_enabled = getattr(config, "ENABLE_BENCHMARKS", False)
        benchmark_time_ms = int((t_end - t_start) * 1000) if benchmark_enabled else None

        total_penalty = sum(f["penalty"] for f in findings)
        final_score = max(0, min(100, 100 - total_penalty))
        avg_complexity = round(sum(complexities) / len(complexities)) if complexities else 0

        return PerformanceResult(
            status="completed",
            score=final_score,
            functions=total_functions,
            loops=total_loops,
            nested_loops=nested_loops_count,
            average_complexity=avg_complexity,
            benchmark_enabled=benchmark_enabled,
            benchmark_time_ms=benchmark_time_ms,
            findings=findings,
        )

    def _analyze_ast(
        self, tree: ast.AST, rel_path: str, is_small_repo: bool
    ) -> tuple[list[dict[str, Any]], int, int, int, list[int]]:
        findings: list[dict[str, Any]] = []
        function_count = 0
        loop_count = 0
        nested_loop_count = 0
        complexities: list[int] = []

        def add_finding(rule: str, severity: str, message: str, penalty: int, line: int | None):
            findings.append(
                {
                    "rule": rule,
                    "severity": severity,
                    "file_path": rel_path,
                    "line": line,
                    "message": message,
                    "penalty": penalty,
                }
            )

        # Traverse AST for functions and top-level constructs
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_count += 1
                comp = calculate_complexity(node)
                complexities.append(comp)

                # PERF008: Very large functions (> 250 lines)
                start_line = getattr(node, "lineno", 1)
                end_line = getattr(node, "end_lineno", start_line)
                line_count = end_line - start_line + 1

                excessive_lines = line_count > 500 if is_small_repo else line_count > 250
                if line_count > 250 and (not is_small_repo or excessive_lines):
                    add_finding(
                        "PERF008",
                        "Medium",
                        f"Very large function '{node.name}' ({line_count} lines).",
                        5,
                        start_line,
                    )

                # PERF009: High cyclomatic complexity (> 20)
                excessive_comp = comp > 40 if is_small_repo else comp > 20
                if comp > 20 and (not is_small_repo or excessive_comp):
                    add_finding(
                        "PERF009",
                        "Medium",
                        f"High cyclomatic complexity ({comp}) in function '{node.name}'.",
                        6,
                        start_line,
                    )

                # PERF007: Blocking sleep in routes/views
                if is_route_or_view(node, rel_path):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call):
                            func_name = ""
                            if isinstance(sub.func, ast.Attribute):
                                func_name = f"{getattr(sub.func.value, 'id', '')}.{sub.func.attr}"
                            elif isinstance(sub.func, ast.Name):
                                func_name = sub.func.id

                            if func_name in ("time.sleep", "asyncio.sleep", "sleep"):
                                add_finding(
                                    "PERF007",
                                    "Medium",
                                    f"Blocking sleep '{func_name}' in route handler or view '{node.name}'.",
                                    8,
                                    getattr(sub, "lineno", start_line),
                                )

                # PERF010: Duplicate expensive computation inside function
                calls_seen: dict[str, list[ast.Call]] = {}
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        # Filter for function calls with arguments or known expensive routines
                        try:
                            call_str = ast.unparse(sub)
                        except Exception:
                            continue
                        if len(call_str) > 4 and sub.args:
                            calls_seen.setdefault(call_str, []).append(sub)

                for call_str, call_nodes in calls_seen.items():
                    if len(call_nodes) > 1:
                        # Add finding for duplicate calls after the first
                        for dup_node in call_nodes[1:]:
                            add_finding(
                                "PERF010",
                                "Medium",
                                f"Duplicate expensive computation '{call_str}' detected.",
                                5,
                                getattr(dup_node, "lineno", start_line),
                            )

        # Loop analysis (PERF001 - PERF006)
        def inspect_loops(node: ast.AST, loop_depth: int = 0):
            nonlocal loop_count, nested_loop_count
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                    loop_count += 1
                    current_depth = loop_depth + 1
                    line = getattr(child, "lineno", None)

                    if current_depth > 1:
                        nested_loop_count += 1
                        add_finding(
                            "PERF001",
                            "Medium",
                            f"Nested loop detected (depth {current_depth}).",
                            8,
                            line,
                        )

                    # Inspect body of loop for loop anti-patterns
                    for sub in ast.walk(child):
                        if sub is child:
                            continue

                        # Avoid triggering loop body findings for inner nested loops to prevent noise
                        if isinstance(sub, (ast.For, ast.AsyncFor, ast.While)):
                            continue

                        # PERF003: Database queries inside loops
                        if isinstance(sub, ast.Call):
                            is_db_query = False
                            if isinstance(sub.func, ast.Attribute):
                                attr = sub.func.attr
                                obj_name = getattr(sub.func.value, "id", "") or getattr(
                                    sub.func.value, "attr", ""
                                )
                                if attr in ("query", "execute", "fetchall", "fetchone") or obj_name in (
                                    "session",
                                    "cursor",
                                    "Model",
                                ):
                                    is_db_query = True
                            elif isinstance(sub.func, ast.Name):
                                if sub.func.id in ("execute", "fetchall", "fetchone"):
                                    is_db_query = True

                            if is_db_query:
                                add_finding(
                                    "PERF003",
                                    "High",
                                    "Database query inside loop detected.",
                                    12,
                                    getattr(sub, "lineno", line),
                                )
                                continue

                        # PERF004: Repeated file opening inside loops
                        if isinstance(sub, ast.Call):
                            is_open = False
                            if isinstance(sub.func, ast.Name) and sub.func.id == "open":
                                is_open = True
                            elif isinstance(sub.func, ast.Attribute) and sub.func.attr == "open":
                                is_open = True

                            if is_open:
                                add_finding(
                                    "PERF004",
                                    "Medium",
                                    "Repeated file opening inside loop detected.",
                                    8,
                                    getattr(sub, "lineno", line),
                                )
                                continue

                        # PERF006: Repeated sorting inside loops
                        if isinstance(sub, ast.Call):
                            is_sort = False
                            if isinstance(sub.func, ast.Name) and sub.func.id == "sorted":
                                is_sort = True
                            elif isinstance(sub.func, ast.Attribute) and sub.func.attr == "sort":
                                is_sort = True

                            if is_sort:
                                add_finding(
                                    "PERF006",
                                    "Medium",
                                    "Repeated sorting inside loop detected.",
                                    5,
                                    getattr(sub, "lineno", line),
                                )
                                continue

                        # PERF005: Large object allocations inside loops
                        is_alloc = False
                        if isinstance(sub, (ast.List, ast.Dict)):
                            is_alloc = True
                        elif isinstance(sub, ast.Call):
                            if isinstance(sub.func, ast.Name) and sub.func.id in ("list", "dict", "set"):
                                is_alloc = True
                            elif isinstance(sub.func, ast.Attribute):
                                attr = sub.func.attr
                                mod = getattr(sub.func.value, "id", "")
                                if attr in ("array", "DataFrame") and mod in (
                                    "numpy",
                                    "np",
                                    "pandas",
                                    "pd",
                                ):
                                    is_alloc = True

                        if is_alloc:
                            add_finding(
                                "PERF005",
                                "Medium",
                                "Large object allocation inside loop detected.",
                                5,
                                getattr(sub, "lineno", line),
                            )
                            continue

                        # PERF002: Repeated expensive operations inside loops
                        if isinstance(sub, ast.Call):
                            if isinstance(sub.func, ast.Name) and sub.func.id in (
                                "len",
                                "sum",
                                "tuple",
                                "max",
                                "min",
                            ):
                                add_finding(
                                    "PERF002",
                                    "Medium",
                                    f"Repeated expensive operation '{sub.func.id}()' inside loop detected.",
                                    5,
                                    getattr(sub, "lineno", line),
                                )

                    inspect_loops(child, current_depth)
                else:
                    inspect_loops(child, loop_depth)

        inspect_loops(tree)
        return findings, function_count, loop_count, nested_loop_count, complexities
