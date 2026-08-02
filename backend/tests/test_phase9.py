"""Phase 9 Automated Regression & Integration Test Suite.

Tests static architecture analysis, evidence collection, import graph construction,
circular dependency detection, small repository handling, scoring, persistence,
API endpoints, derived snapshot lineage, and backward compatibility.
"""

import io
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest

from app import config
from app.models import ArchitectureAnalysis, ArchitectureFinding, CategoryScore, Evaluation
from app.services.architecture_analyzer import ArchitectureAnalyzer


def make_zip(files_dict: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, content in files_dict.items():
            zf.writestr(fname, content)
    return buf.getvalue()


# 1. test_architecture_analyzer_completes
def test_architecture_analyzer_completes(tmp_path):
    (tmp_path / "app.py").write_text("def run(): pass\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.status == "completed"
    assert res.score == 100
    assert res.source_file_count == 1


# 2. test_repository_relative_paths
def test_repository_relative_paths(tmp_path):
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "user_service.py").write_text("import services.user_service\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    for f in res.findings:
        assert not f["file_path"].startswith("C:")
        assert not f["file_path"].startswith("/")
        assert f["file_path"] == "services/user_service.py"


# 3. test_module_detection
def test_module_detection(tmp_path):
    (tmp_path / "mod_a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "mod_b.py").write_text("y = 2\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.module_count == 2
    assert res.source_file_count == 2


# 4. test_package_detection
def test_package_detection(tmp_path):
    pkg = tmp_path / "mypackage"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("# init\n", encoding="utf-8")
    (pkg / "core.py").write_text("def f(): pass\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.package_count == 1


# 5. test_internal_import_graph
def test_internal_import_graph(tmp_path):
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 10\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.dependency_edge_count == 1
    assert res.circular_dependency_count == 0


# 6. test_external_imports_ignored
def test_external_imports_ignored(tmp_path):
    (tmp_path / "main.py").write_text("import os\nimport sys\nimport fastapi\nimport sqlalchemy\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.dependency_edge_count == 0
    assert res.circular_dependency_count == 0


# 7. test_circular_dependency_detection
def test_circular_dependency_detection(tmp_path):
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import a\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.circular_dependency_count == 1
    assert any(f["rule_id"] == "ARCH001" for f in res.findings)
    assert res.score == 88  # 100 - 12 penalty


# 8. test_no_cycle_repository
def test_no_cycle_repository(tmp_path):
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import c\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("x = 1\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.circular_dependency_count == 0
    assert res.dependency_edge_count == 2
    assert res.score == 100


# 9. test_excessive_module_size
def test_excessive_module_size(tmp_path):
    (tmp_path / "m1.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "m2.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("x = 1\n" * 600, encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert any(f["rule_id"] == "ARCH002" for f in res.findings)


# 10. test_fan_out_detection
def test_fan_out_detection(tmp_path):
    for i in range(10):
        (tmp_path / f"m{i}.py").write_text(f"v_{i} = {i}\n", encoding="utf-8")
    imports = "\n".join(f"import m{i}" for i in range(9))
    (tmp_path / "hub.py").write_text(imports + "\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.high_fan_out_count == 1
    assert any(f["rule_id"] == "ARCH003" for f in res.findings)


# 11. test_small_repository_not_unfairly_penalized
def test_small_repository_not_unfairly_penalized(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text("from calc import add\ndef test_add(): assert add(1, 1) == 2\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.score == 100
    assert res.status == "completed"


# 12. test_architecture_documentation_detection
def test_architecture_documentation_detection(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("z = 3\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project Structure\nThis document describes the system architecture.\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert res.architecture_docs_present is True
    assert not any(f["rule_id"] == "ARCH006" for f in res.findings)


# 13. test_architecture_score_calculation
def test_architecture_score_calculation(tmp_path):
    # Create 2 circular dependencies
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import a\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    # Deductions: 1 cycle (12 pts) -> score = 88
    assert res.score == 88


# 14. test_architecture_score_clamped_0_100
def test_architecture_score_clamped_0_100(tmp_path):
    for i in range(10):
        prev = (i - 1) % 10
        nxt = (i + 1) % 10
        (tmp_path / f"m{i}.py").write_text(f"import m{prev}\nimport m{nxt}\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer()
    res = analyzer._analyze_workspace(tmp_path)
    assert 0 <= res.score <= 100


# 15. test_architecture_not_measured_on_failure
def test_architecture_not_measured_on_failure(client):
    files = {"data.txt": "hello\n"}
    upload = client.post("/api/projects", files={"file": ("nodata.zip", make_zip(files), "application/zip")})
    project_id = upload.json()["project_id"]
    eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

    client.post(f"/api/evaluations/{eval_id}/run")
    score_resp = client.post(f"/api/evaluations/{eval_id}/score").json()
    print("\nDEBUG score_resp:", score_resp)
    categories = score_resp if isinstance(score_resp, list) else score_resp.get("categories", [])
    arch_score = next((c for c in categories if c["category"] == "architecture"), None)
    assert arch_score is not None
    assert arch_score["status"] == "not_measured"
    assert arch_score["score"] is None


# 16. test_architecture_persisted
def test_architecture_persisted(client, db_session):
    files = {"a.py": "def run(): pass\n"}
    upload = client.post("/api/projects", files={"file": ("arch_persist.zip", make_zip(files), "application/zip")})
    project_id = upload.json()["project_id"]
    eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

    client.post(f"/api/evaluations/{eval_id}/run")
    client.post(f"/api/evaluations/{eval_id}/score")

    record = db_session.query(ArchitectureAnalysis).filter_by(evaluation_id=eval_id).first()
    assert record is not None
    assert record.status == "completed"
    assert record.score == 100


# 17. test_report_endpoint_integration
def test_report_endpoint_integration(client):
    files = {
        "a.py": "import b\n",
        "b.py": "import a\n"
    }
    upload = client.post("/api/projects", files={"file": ("arch_report.zip", make_zip(files), "application/zip")})
    project_id = upload.json()["project_id"]
    eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

    client.post(f"/api/evaluations/{eval_id}/run")
    client.post(f"/api/evaluations/{eval_id}/score")

    report = client.get(f"/api/evaluations/{eval_id}/report").json()
    assert report["scoring_version"] in ("1.2", "1.3")
    assert report["overall"]["measured_categories"] in (3, 4)  # maintainability, security, architecture, performance measured
    assert report["overall"]["total_categories"] == 6

    arch_data = report["architecture_analysis"]
    assert arch_data is not None
    assert arch_data["status"] == "completed"
    assert arch_data["metrics"]["circular_dependency_count"] == 1
    assert len(arch_data["findings"]) == 1


# 18. test_architecture_endpoint_integration
def test_architecture_endpoint_integration(client):
    files = {"app.py": "def main(): pass\n"}
    upload = client.post("/api/projects", files={"file": ("arch_ep.zip", make_zip(files), "application/zip")})
    project_id = upload.json()["project_id"]
    eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

    client.post(f"/api/evaluations/{eval_id}/run")

    res = client.get(f"/api/evaluations/{eval_id}/architecture")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["score"] == 100
    assert data["metrics"]["source_file_count"] == 1


# 19. test_derived_snapshot_architecture_analysis
def test_derived_snapshot_architecture_analysis(client, db_session):
    files = {
        "app.py": "import math\nimport os\nprint(os.name)\n",
        "services.py": "import models\n",
        "models.py": "import services\n"
    }
    upload = client.post("/api/projects", files={"file": ("derived_arch.zip", make_zip(files), "application/zip")})
    project_id = upload.json()["project_id"]
    eval_orig = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

    client.post(f"/api/evaluations/{eval_orig}/run")
    client.post(f"/api/evaluations/{eval_orig}/score")

    recs = client.post(f"/api/evaluations/{eval_orig}/recommendations").json()
    f401_rec = next(r for r in recs if r["rule_id"] == "F401")
    preview = client.post(f"/api/recommendations/{f401_rec['id']}/preview").json()
    apply_res = client.post(f"/api/fixes/{preview['id']}/apply").json()
    derived_snap_id = apply_res["derived_snapshot_id"]

    verify_res = client.post(f"/api/fixes/{preview['id']}/verify").json()
    ver_eval_id = verify_res["verification_evaluation_id"]

    v_report = client.get(f"/api/evaluations/{ver_eval_id}/report").json()
    v_arch = v_report["architecture_analysis"]
    assert v_arch["status"] == "completed"
    assert v_arch["metrics"]["circular_dependency_count"] == 1


# 20. test_report_refresh_does_not_rerun_analysis
def test_report_refresh_does_not_rerun_analysis(client):
    files = {"a.py": "x = 1\n"}
    upload = client.post("/api/projects", files={"file": ("refresh_arch.zip", make_zip(files), "application/zip")})
    project_id = upload.json()["project_id"]
    eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

    client.post(f"/api/evaluations/{eval_id}/run")
    client.post(f"/api/evaluations/{eval_id}/score")

    r1 = client.get(f"/api/evaluations/{eval_id}/architecture").json()
    r2 = client.get(f"/api/evaluations/{eval_id}/architecture").json()

    assert r1["id"] == r2["id"]


# 21. test_phase8_correctness_testing_remains_unchanged
def test_phase8_correctness_testing_remains_unchanged(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "calc.py": "def add(a, b): return a + b\n",
            "tests/test_calc.py": "from calc import add\ndef test_add(): assert add(1, 1) == 2\n"
        }
        upload = client.post("/api/projects", files={"file": ("p8_p9.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        client.post(f"/api/evaluations/{eval_id}/score")

        report = client.get(f"/api/evaluations/{eval_id}/report").json()
        assert report["overall"]["measured_categories"] in (5, 6)  # Maintainability, Security, Correctness, Testing, Architecture, Performance
        assert report["overall"]["total_categories"] == 6
        assert report["test_run"]["tests_passed"] == 1
        assert report["architecture_analysis"]["status"] == "completed"


# 22. test_phase1_8_regression_compatibility
def test_phase1_8_regression_compatibility(client):
    files = {"app.py": "import os\n"}
    upload = client.post("/api/projects", files={"file": ("reg_compat.zip", make_zip(files), "application/zip")})
    project_id = upload.json()["project_id"]
    eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

    run_res = client.post(f"/api/evaluations/{eval_id}/run")
    assert run_res.status_code == 200
    assert run_res.json()["status"] in ("completed", "completed_with_errors")

    score_res = client.post(f"/api/evaluations/{eval_id}/score")
    assert score_res.status_code == 200
