"""
Phase 8: Safe Controlled Test Runner Service.

Important Security Architecture Note:
When ENABLE_LOCAL_TEST_EXECUTION is False (default), test discovery occurs statically
and test execution is BLOCKED. Correctness and Testing scores remain Not measured.

When ENABLE_LOCAL_TEST_EXECUTION is True, LocalTestRunner acts as a CONTROLLED LOCAL DEVELOPMENT RUNNER.
It is NOT a secure sandbox or OS-level isolation layer; it runs Python with the permissions
of the backend process. Production/untrusted execution requires a container/VM sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from sqlalchemy.orm import Session

from .. import config
from ..models import AgentEvent, TestFailure, TestRun
from .project_detector import ProjectDetector


@dataclass
class FailureDetail:
    __test__ = False
    node_id: str
    file_path: str
    test_name: str
    failure_type: str
    message: str


@dataclass
class TestResult:
    __test__ = False
    status: str  # not_discovered, no_tests, blocked, dependency_unavailable, completed, timeout, execution_error
    framework: str = "pytest"
    tests_collected: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_errors: int = 0
    duration_ms: int | None = None
    coverage_percent: float | None = None
    execution_mode: str = "local_development"
    blocked_reason: str | None = None
    exit_code: int | None = None
    stdout_summary: str | None = None
    stderr_summary: str | None = None
    failures: list[FailureDetail] | None = None

    def __post_init__(self):
        if self.failures is None:
            self.failures = []


def sanitize_relative_path(file_path: str | None, workspace: Path) -> str:
    """Ensure paths returned by API/DB are repository-relative and use forward slashes."""
    if not file_path:
        return ""
    
    clean_fp = file_path.replace("\\", "/")
    ws_clean = str(workspace.resolve()).replace("\\", "/")

    if clean_fp.startswith(ws_clean):
        clean_fp = clean_fp[len(ws_clean):].lstrip("/")

    p = Path(clean_fp)
    try:
        if p.is_absolute():
            clean_fp = p.relative_to(workspace).as_posix()
    except Exception:
        pass

    if not clean_fp.endswith(".py") and "." in clean_fp and "/" not in clean_fp:
        clean_fp = clean_fp.replace(".", "/") + ".py"

    return clean_fp


class TestRunner:
    __test__ = False
    """Controlled test discovery and execution abstraction."""

    def run_tests(self, db: Session, evaluation_id: str, snapshot_id: str, workspace_path: str | Path) -> TestRun:
        workspace = Path(workspace_path).resolve()

        # Check path traversal
        workspaces_root = (config.DATA_DIR / "workspaces").resolve()
        if not str(workspace).startswith(str(workspaces_root)):
            raise ValueError("Snapshot workspace path is outside workspace root.")

        detector = ProjectDetector()
        detection = detector.inspect(workspace)

        # Discovery check
        test_files_count = detection.test_file_count
        pytest_detected = any(tf.get("name") == "pytest" for tf in detection.test_frameworks) or test_files_count > 0

        # Create AgentEvent for discovery
        db.add(AgentEvent(
            evaluation_id=evaluation_id,
            stage="TEST_DISCOVERY",
            status="started",
            message="Test discovery started",
            metadata_json={"test_file_count": test_files_count}
        ))
        db.commit()

        if not pytest_detected and test_files_count == 0:
            db.add(AgentEvent(
                evaluation_id=evaluation_id,
                stage="TEST_DISCOVERY",
                status="completed",
                message="No tests discovered",
                metadata_json={"test_file_count": 0}
            ))
            db.commit()

            test_run = TestRun(
                evaluation_id=evaluation_id,
                snapshot_id=snapshot_id,
                framework="pytest",
                status="no_tests",
                tests_collected=0,
                execution_mode="local_development" if config.ENABLE_LOCAL_TEST_EXECUTION else "disabled",
                blocked_reason="No automated tests discovered."
            )
            db.add(test_run)
            db.commit()
            return test_run

        db.add(AgentEvent(
            evaluation_id=evaluation_id,
            stage="TEST_DISCOVERY",
            status="completed",
            message=f"Test discovery completed: {test_files_count} test file(s) found",
            metadata_json={"test_file_count": test_files_count, "framework": "pytest"}
        ))
        db.commit()

        # Execution policy check
        if not config.ENABLE_LOCAL_TEST_EXECUTION:
            db.add(AgentEvent(
                evaluation_id=evaluation_id,
                stage="TEST_EXECUTION",
                status="blocked",
                message="Test execution blocked by safety policy",
                metadata_json={"reason": "CODEEVAL_ENABLE_LOCAL_TEST_EXECUTION is false"}
            ))
            db.commit()

            test_run = TestRun(
                evaluation_id=evaluation_id,
                snapshot_id=snapshot_id,
                framework="pytest",
                status="blocked",
                tests_collected=test_files_count,
                execution_mode="disabled",
                blocked_reason="Safe test execution environment is not enabled."
            )
            db.add(test_run)
            db.commit()
            return test_run

        # Execute tests via LocalTestRunner
        db.add(AgentEvent(
            evaluation_id=evaluation_id,
            stage="TEST_EXECUTION",
            status="started",
            message="Test execution started",
            metadata_json={"execution_mode": "local_development"}
        ))
        db.commit()

        res = self._execute_pytest_local(workspace)

        if res.coverage_percent is not None:
            db.add(AgentEvent(
                evaluation_id=evaluation_id,
                stage="COVERAGE",
                status="completed",
                message=f"Coverage analysis completed: {res.coverage_percent}%",
                metadata_json={"coverage_percent": res.coverage_percent}
            ))
        else:
            db.add(AgentEvent(
                evaluation_id=evaluation_id,
                stage="COVERAGE",
                status="skipped",
                message="Coverage analysis unavailable",
                metadata_json={"reason": "Coverage package unavailable or collection failed"}
            ))

        db.add(AgentEvent(
            evaluation_id=evaluation_id,
            stage="TEST_EXECUTION",
            status="completed" if res.status == "completed" else "failed",
            message=f"Test execution {res.status}: {res.tests_passed} passed, {res.tests_failed} failed, {res.tests_errors} errors",
            metadata_json={"status": res.status, "collected": res.tests_collected, "passed": res.tests_passed, "failed": res.tests_failed}
        ))

        test_run = TestRun(
            evaluation_id=evaluation_id,
            snapshot_id=snapshot_id,
            framework=res.framework,
            status=res.status,
            tests_collected=res.tests_collected,
            tests_passed=res.tests_passed,
            tests_failed=res.tests_failed,
            tests_skipped=res.tests_skipped,
            tests_errors=res.tests_errors,
            duration_ms=res.duration_ms,
            coverage_percent=res.coverage_percent,
            execution_mode=res.execution_mode,
            blocked_reason=res.blocked_reason,
            exit_code=res.exit_code,
            stdout_summary=res.stdout_summary,
            stderr_summary=res.stderr_summary
        )
        db.add(test_run)
        db.flush()

        if res.failures:
            for f in res.failures:
                db.add(TestFailure(
                    test_run_id=test_run.id,
                    node_id=f.node_id,
                    file_path=sanitize_relative_path(f.file_path, workspace),
                    test_name=f.test_name,
                    failure_type=f.failure_type,
                    message=f.message
                ))

        db.commit()
        return test_run

    def _execute_pytest_local(self, workspace: Path) -> TestResult:
        python_exe = sys.executable

        # Minimal safe environment
        env = {
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(workspace),
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "WINDIR": os.environ.get("WINDIR", ""),
            "TMP": os.environ.get("TMP", ""),
            "TEMP": os.environ.get("TEMP", ""),
        }

        # Check coverage availability
        has_coverage = False
        try:
            cov_check = subprocess.run(
                [python_exe, "-c", "import coverage"],
                cwd=str(workspace),
                env=env,
                capture_output=True,
                timeout=5
            )
            has_coverage = cov_check.returncode == 0
        except Exception:
            has_coverage = False

        with tempfile.TemporaryDirectory() as tmpdir:
            junit_xml = Path(tmpdir) / "junit_results.xml"
            cov_file = Path(tmpdir) / ".coverage"
            cov_json = Path(tmpdir) / "coverage.json"

            cmd = [python_exe]
            if has_coverage:
                cmd.extend(["-m", "coverage", "run", f"--data-file={cov_file}", "--source=.", "-m", "pytest"])
            else:
                cmd.extend(["-m", "pytest"])

            cmd.extend([
                "-o", "rootdir=.",
                "-o", "norecursedirs=.venv node_modules __pycache__",
                f"--junitxml={junit_xml}",
                "-o", "junit_family=xunit2",
                "--tb=short",
                "-q",
                "."
            ])

            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(workspace),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                try:
                    stdout, stderr = proc.communicate(timeout=config.TEST_TIMEOUT_SECONDS)
                    exit_code = proc.returncode
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                    return TestResult(
                        status="timeout",
                        execution_mode="local_development",
                        blocked_reason=f"Test execution timed out after {config.TEST_TIMEOUT_SECONDS} seconds.",
                        stdout_summary="Timeout expired.",
                        stderr_summary="Process terminated due to timeout."
                    )
            except Exception as err:
                return TestResult(
                    status="execution_error",
                    execution_mode="local_development",
                    blocked_reason=f"Failed to launch test runner: {err}",
                    stdout_summary="",
                    stderr_summary=str(err)
                )

            stdout_bounded = stdout[:config.MAX_OUTPUT_BYTES] if stdout else ""
            stderr_bounded = stderr[:config.MAX_OUTPUT_BYTES] if stderr else ""

            # Check if pytest failed due to missing module/dependency error
            if exit_code in (2, 3, 4) and not junit_xml.exists():
                if "ModuleNotFoundError" in stderr or "ImportError" in stderr or "ModuleNotFoundError" in stdout or "ImportError" in stdout:
                    return TestResult(
                        status="dependency_unavailable",
                        execution_mode="local_development",
                        blocked_reason="Required Python module or dependency unavailable in test environment.",
                        exit_code=exit_code,
                        stdout_summary=stdout_bounded,
                        stderr_summary=stderr_bounded
                    )

            # Parse Coverage if available
            coverage_pct = None
            if has_coverage and cov_file.exists():
                try:
                    cov_report = subprocess.run(
                        [python_exe, "-m", "coverage", "json", f"--data-file={cov_file}", "-o", str(cov_json), "--omit=tests/*,test/*,*_test.py,test_*.py"],
                        cwd=str(workspace),
                        env=env,
                        capture_output=True,
                        timeout=10
                    )
                    if cov_report.returncode == 0 and cov_json.exists():
                        cov_data = json.loads(cov_json.read_text(encoding="utf-8"))
                        totals = cov_data.get("totals", {})
                        pct = totals.get("percent_covered")
                        if pct is not None:
                            coverage_pct = round(float(pct), 1)
                except Exception:
                    coverage_pct = None

            # Parse JUnit XML
            if not junit_xml.exists():
                return TestResult(
                    status="execution_error",
                    execution_mode="local_development",
                    blocked_reason="pytest did not generate XML result output.",
                    exit_code=exit_code,
                    stdout_summary=stdout_bounded,
                    stderr_summary=stderr_bounded
                )

            try:
                tree = ET.parse(junit_xml)
                root = tree.getroot()

                suites = [root] if root.tag == "testsuite" else root.findall("testsuite")

                collected, passed, failed, errors, skipped = 0, 0, 0, 0, 0
                duration_sec = 0.0
                failures_list: list[FailureDetail] = []

                for suite in suites:
                    collected += int(suite.attrib.get("tests", 0))
                    failures_count = int(suite.attrib.get("failures", 0))
                    errors_count = int(suite.attrib.get("errors", 0))
                    skipped_count = int(suite.attrib.get("skipped", 0))
                    duration_sec += float(suite.attrib.get("time", 0.0))

                    failed += failures_count
                    errors += errors_count
                    skipped += skipped_count

                    for testcase in suite.findall("testcase"):
                        name = testcase.attrib.get("name", "unknown_test")
                        file_raw = testcase.attrib.get("file") or testcase.attrib.get("classname", "")
                        file_rel = sanitize_relative_path(file_raw, workspace)
                        node_id = f"{file_rel}::{name}"

                        failure_elem = testcase.find("failure")
                        error_elem = testcase.find("error")

                        problem_elem = failure_elem if failure_elem is not None else error_elem
                        if problem_elem is not None:
                            ftype = problem_elem.attrib.get("type", problem_elem.tag)
                            msg = problem_elem.attrib.get("message") or problem_elem.text or "Test failed"
                            # Strip absolute workspace directory paths from message
                            msg_sanitized = msg.replace(str(workspace), "").replace(str(workspace.resolve()), "")
                            msg_bounded = msg_sanitized[:2000]

                            failures_list.append(FailureDetail(
                                node_id=node_id,
                                file_path=file_rel,
                                test_name=name,
                                failure_type=ftype,
                                message=msg_bounded
                            ))

                passed = max(0, collected - (failed + errors + skipped))
                duration_ms = int(duration_sec * 1000)

                if collected == 0 or (passed == 0 and failed == 0 and errors == 0 and skipped == 0):
                    return TestResult(
                        status="no_tests_collected",
                        framework="pytest",
                        tests_collected=0,
                        tests_passed=0,
                        tests_failed=0,
                        tests_skipped=0,
                        tests_errors=0,
                        duration_ms=duration_ms,
                        coverage_percent=None,
                        execution_mode="local_development",
                        blocked_reason="pytest collected 0 tests during execution.",
                        exit_code=exit_code,
                        stdout_summary=stdout_bounded,
                        stderr_summary=stderr_bounded,
                        failures=[]
                    )

                return TestResult(
                    status="completed",
                    framework="pytest",
                    tests_collected=collected,
                    tests_passed=passed,
                    tests_failed=failed,
                    tests_skipped=skipped,
                    tests_errors=errors,
                    duration_ms=duration_ms,
                    coverage_percent=coverage_pct,
                    execution_mode="local_development",
                    exit_code=exit_code,
                    stdout_summary=stdout_bounded,
                    stderr_summary=stderr_bounded,
                    failures=failures_list
                )

            except Exception as parse_err:
                return TestResult(
                    status="execution_error",
                    execution_mode="local_development",
                    blocked_reason=f"Failed to parse test XML results: {parse_err}",
                    exit_code=exit_code,
                    stdout_summary=stdout_bounded,
                    stderr_summary=stderr_bounded
                )
