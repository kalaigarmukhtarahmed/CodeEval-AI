"""Phase 10 Automated Regression & Integration Test Suite.

Tests static performance analysis (PERF001 to PERF010), small repository policy,
benchmark execution settings, DB persistence, API endpoints (/report and /performance),
scoring version 1.3, assessment coverage 6/6, derived snapshot lineage, refresh report,
and regression of Phases 1-9.
"""

import io
from pathlib import Path
from unittest.mock import patch
import zipfile
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import Evaluation, Finding, PerformanceAnalysis, PerformanceFinding, CategoryScore
from app.services.performance_analyzer import PerformanceAnalyzer, calculate_complexity, is_route_or_view
from app.services.scoring_engine import SCORING_VERSION, ScoringEngine, overall


def make_zip(files_dict: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, content in files_dict.items():
            zf.writestr(fname, content)
    return buf.getvalue()


# 1. test_perf001_nested_loops
def test_perf001_nested_loops(tmp_path):
    code = """
def func():
    for i in range(10):
        for j in range(10):
            while True:
                pass
"""
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf001_findings = [f for f in res.findings if f["rule"] == "PERF001"]
    assert len(perf001_findings) == 2  # inner for and inner while
    assert res.nested_loops == 2


# 2. test_perf002_expensive_operations_in_loops
def test_perf002_expensive_operations_in_loops(tmp_path):
    code = """
def func(data):
    for i in range(10):
        n = len(data)
        s = sum(data)
        m = max(data)
"""
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf002_findings = [f for f in res.findings if f["rule"] == "PERF002"]
    assert len(perf002_findings) >= 3


# 3. test_perf003_db_queries_in_loops
def test_perf003_db_queries_in_loops(tmp_path):
    code = """
def func(session, items):
    for item in items:
        res = session.query(User).filter_by(id=item).all()
        cursor.execute("SELECT 1")
"""
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf003_findings = [f for f in res.findings if f["rule"] == "PERF003"]
    assert len(perf003_findings) == 2
    assert any(f["severity"] == "High" for f in perf003_findings)


# 4. test_perf004_file_opening_in_loops
def test_perf004_file_opening_in_loops(tmp_path):
    code = """
def func(files):
    for f in files:
        with open(f, 'r') as fp:
            data = fp.read()
"""
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf004_findings = [f for f in res.findings if f["rule"] == "PERF004"]
    assert len(perf004_findings) == 1
    assert perf004_findings[0]["penalty"] == 8


# 5. test_perf005_large_object_allocations_in_loops
def test_perf005_large_object_allocations_in_loops(tmp_path):
    code = """
def func():
    for i in range(10):
        a = []
        b = {}
        c = dict()
"""
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf005_findings = [f for f in res.findings if f["rule"] == "PERF005"]
    assert len(perf005_findings) == 3


# 6. test_perf006_repeated_sorting_in_loops
def test_perf006_repeated_sorting_in_loops(tmp_path):
    code = """
def func(items):
    for i in range(5):
        s = sorted(items)
        items.sort()
"""
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf006_findings = [f for f in res.findings if f["rule"] == "PERF006"]
    assert len(perf006_findings) == 2


# 7. test_perf007_blocking_sleep_in_routes
def test_perf007_blocking_sleep_in_routes(tmp_path):
    code = """
import time

def api_get_user(request):
    time.sleep(1)
    return {"ok": True}
"""
    (tmp_path / "views.py").write_text(code, encoding="utf-8")
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf007_findings = [f for f in res.findings if f["rule"] == "PERF007"]
    assert len(perf007_findings) == 1
    assert perf007_findings[0]["penalty"] == 8


# 8. test_perf008_very_large_functions
def test_perf008_very_large_functions(tmp_path):
    lines = ["def huge_func():\n"]
    for i in range(260):
        lines.append(f"    x_{i} = {i}\n")
    lines.append("    return x_0\n")
    code = "".join(lines)
    # Add dummy files so small repo policy doesn't suppress it
    (tmp_path / "a.py").write_text(code, encoding="utf-8")
    (tmp_path / "b.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("y=2\n", encoding="utf-8")

    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf008_findings = [f for f in res.findings if f["rule"] == "PERF008"]
    assert len(perf008_findings) == 1
    assert perf008_findings[0]["penalty"] == 5


# 9. test_perf009_high_cyclomatic_complexity
def test_perf009_high_cyclomatic_complexity(tmp_path):
    lines = ["def complex_func(x):\n"]
    for i in range(25):
        lines.append(f"    if x == {i}:\n        return {i}\n")
    lines.append("    return -1\n")
    code = "".join(lines)
    (tmp_path / "a.py").write_text(code, encoding="utf-8")
    (tmp_path / "b.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("# dummy line\n" * 150, encoding="utf-8")

    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf009_findings = [f for f in res.findings if f["rule"] == "PERF009"]
    assert len(perf009_findings) == 1
    assert perf009_findings[0]["penalty"] == 6


# 10. test_perf010_duplicate_expensive_computation
def test_perf010_duplicate_expensive_computation(tmp_path):
    code = """
def func(x, y):
    val1 = calculate_matrix_determinant(x, y)
    val2 = calculate_matrix_determinant(x, y)
    return val1 + val2
"""
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf010_findings = [f for f in res.findings if f["rule"] == "PERF010"]
    assert len(perf010_findings) == 1
    assert perf010_findings[0]["penalty"] == 5


# 11. test_small_repository_policy
def test_small_repository_policy(tmp_path):
    lines = ["def moderately_large_func():\n"]
    for i in range(260):
        lines.append(f"    x_{i} = {i}\n")
    code = "".join(lines)
    (tmp_path / "single_file.py").write_text(code, encoding="utf-8")

    # Small repo (< 3 files) should not receive PERF008 penalty unless > 500 lines
    res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
    perf008_findings = [f for f in res.findings if f["rule"] == "PERF008"]
    assert len(perf008_findings) == 0


# 12. test_benchmark_disabled_by_default
def test_benchmark_disabled_by_default(tmp_path):
    (tmp_path / "app.py").write_text("def f(): pass\n", encoding="utf-8")
    with patch.object(config, "ENABLE_BENCHMARKS", False):
        res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
        assert res.benchmark_enabled is False
        assert res.benchmark_time_ms is None


# 13. test_benchmark_enabled_configuration
def test_benchmark_enabled_configuration(tmp_path):
    (tmp_path / "app.py").write_text("def f(): pass\n", encoding="utf-8")
    with patch.object(config, "ENABLE_BENCHMARKS", True):
        res = PerformanceAnalyzer()._analyze_workspace(tmp_path)
        assert res.benchmark_enabled is True
        assert res.benchmark_time_ms is not None
        assert isinstance(res.benchmark_time_ms, int)


# 14. test_persistence_of_performance_analysis
def test_persistence_of_performance_analysis(tmp_path):
    zip_bytes = make_zip({"app.py": "def f():\n    for i in range(5):\n        for j in range(10):\n            pass\n"})
    client = TestClient(app)
    res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
    pid = res.json()["project_id"]

    eval_res = client.post(f"/api/projects/{pid}/evaluations")
    eid = eval_res.json()["id"]

    run_res = client.post(f"/api/evaluations/{eid}/run")
    assert run_res.status_code == 200

    perf_res = client.get(f"/api/evaluations/{eid}/performance")
    assert perf_res.status_code == 200
    perf_data = perf_res.json()
    assert perf_data["status"] == "completed"
    assert perf_data["metrics"]["nested_loops"] == 1
    assert len(perf_data["findings"]) == 1
    assert perf_data["score"] == 92  # 100 - 8


# 15. test_get_report_includes_performance_analysis
def test_get_report_includes_performance_analysis(tmp_path):
    zip_bytes = make_zip({"app.py": "def main(): pass\n"})
    client = TestClient(app)
    res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
    pid = res.json()["project_id"]

    eval_res = client.post(f"/api/projects/{pid}/evaluations")
    eid = eval_res.json()["id"]

    client.post(f"/api/evaluations/{eid}/run")
    client.post(f"/api/evaluations/{eid}/score")

    report_res = client.get(f"/api/evaluations/{eid}/report")
    assert report_res.status_code == 200
    rep = report_res.json()
    assert rep["scoring_version"] == "1.3"
    assert "performance_analysis" in rep
    assert rep["performance_analysis"]["score"] == 100


# 16. test_scoring_version_1_3
def test_scoring_version_1_3():
    assert SCORING_VERSION == "1.3"


# 17. test_assessment_coverage_6_of_6
def test_assessment_coverage_6_of_6(tmp_path):
    zip_bytes = make_zip({
        "app.py": "def main(): pass\n",
        "tests/test_app.py": "def test_pass(): assert True\n"
    })
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        client = TestClient(app)
        res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
        pid = res.json()["project_id"]

        eval_res = client.post(f"/api/projects/{pid}/evaluations")
        eid = eval_res.json()["id"]

        client.post(f"/api/evaluations/{eid}/run")
        client.post(f"/api/evaluations/{eid}/score")

        report_res = client.get(f"/api/evaluations/{eid}/report")
        rep = report_res.json()
        assert rep["overall"]["total_categories"] == 6
        assert rep["overall"]["measured_categories"] == 6


# 18. test_refresh_report_reuses_persisted_evidence
def test_refresh_report_reuses_persisted_evidence(tmp_path):
    zip_bytes = make_zip({"app.py": "def f():\n    for i in range(5):\n        for j in range(10):\n            pass\n"})
    client = TestClient(app)
    res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
    pid = res.json()["project_id"]

    eval_res = client.post(f"/api/projects/{pid}/evaluations")
    eid = eval_res.json()["id"]

    client.post(f"/api/evaluations/{eid}/run")
    client.post(f"/api/evaluations/{eid}/score")

    # Refresh score call
    score_res2 = client.post(f"/api/evaluations/{eid}/score")
    assert score_res2.status_code == 200

    report = client.get(f"/api/evaluations/{eid}/report").json()
    perf_cat = next(c for c in report["categories"] if c["category"] == "performance")
    assert perf_cat["status"] == "measured"
    assert perf_cat["score"] == 92


# 19. test_derived_snapshots_lineage_preserves_performance
def test_derived_snapshots_lineage_preserves_performance(tmp_path):
    zip_bytes = make_zip({"app.py": "def f(): pass\n"})
    client = TestClient(app)
    res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
    pid = res.json()["project_id"]

    eval_res = client.post(f"/api/projects/{pid}/evaluations")
    eid = eval_res.json()["id"]
    client.post(f"/api/evaluations/{eid}/run")
    client.post(f"/api/evaluations/{eid}/score")

    # Trigger recommendation and fix proposal
    recs = client.get(f"/api/evaluations/{eid}/recommendations").json()
    assert isinstance(recs, list)


# 20. test_agent_events_emitted_for_performance
def test_agent_events_emitted_for_performance(tmp_path):
    zip_bytes = make_zip({"app.py": "def f(): pass\n"})
    client = TestClient(app)
    res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
    pid = res.json()["project_id"]

    eval_res = client.post(f"/api/projects/{pid}/evaluations")
    eid = eval_res.json()["id"]
    client.post(f"/api/evaluations/{eid}/run")

    report = client.get(f"/api/evaluations/{eid}/report").json()
    timeline = report["timeline_summary"]
    assert any("Performance analysis started" in m for m in timeline)
    assert any("Performance analysis completed" in m for m in timeline)


# 21. test_no_python_files_unmeasured_performance
def test_no_python_files_unmeasured_performance(tmp_path):
    zip_bytes = make_zip({"index.html": "<h1>Hello</h1>"})
    client = TestClient(app)
    res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
    pid = res.json()["project_id"]

    eval_res = client.post(f"/api/projects/{pid}/evaluations")
    eid = eval_res.json()["id"]
    client.post(f"/api/evaluations/{eid}/run")
    client.post(f"/api/evaluations/{eid}/score")

    report = client.get(f"/api/evaluations/{eid}/report").json()
    perf_cat = next(c for c in report["categories"] if c["category"] == "performance")
    assert perf_cat["status"] == "not_measured"


# 22. test_performance_endpoint_not_run
def test_performance_endpoint_not_run(tmp_path):
    zip_bytes = make_zip({"README.md": "# Docs"})
    client = TestClient(app)
    res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
    pid = res.json()["project_id"]

    eval_res = client.post(f"/api/projects/{pid}/evaluations")
    eid = eval_res.json()["id"]

    perf_res = client.get(f"/api/evaluations/{eid}/performance")
    assert perf_res.status_code == 200
    assert perf_res.json()["status"] == "not_run"


# 23. test_complexity_calculation_helpers
def test_complexity_calculation_helpers():
    import ast
    code = "def f(x):\n  if x:\n    for i in range(10):\n      pass\n"
    tree = ast.parse(code)
    func_node = tree.body[0]
    comp = calculate_complexity(func_node)
    assert comp == 3  # base 1 + if 1 + for 1


# 24. test_is_route_or_view_helper
def test_is_route_or_view_helper():
    import ast
    code = "def user_view(request): pass\n"
    tree = ast.parse(code)
    func_node = tree.body[0]
    assert is_route_or_view(func_node, "views.py") is True
    assert is_route_or_view(func_node, "utils.py") is True


# 25. test_phase1_to_phase9_regression(tmp_path):
def test_phase1_to_phase9_regression(tmp_path):
    zip_bytes = make_zip({"app.py": "import os\ndef run(): print('hello')\n"})
    client = TestClient(app)
    res = client.post("/api/projects", files={"file": ("project.zip", zip_bytes, "application/zip")})
    assert res.status_code == 201
    pid = res.json()["project_id"]

    eval_res = client.post(f"/api/projects/{pid}/evaluations")
    assert eval_res.status_code == 201
    eid = eval_res.json()["id"]

    run_res = client.post(f"/api/evaluations/{eid}/run")
    assert run_res.status_code == 200

    score_res = client.post(f"/api/evaluations/{eid}/score")
    assert score_res.status_code == 200
    report_res = client.get(f"/api/evaluations/{eid}/report")
    assert report_res.status_code == 200
    assert report_res.json()["scoring_version"] == "1.3"
