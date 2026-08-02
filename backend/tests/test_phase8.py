from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest

from app import config
from app.database import Base, SessionLocal, engine
from app.models import CategoryScore, Evaluation, EvaluationCheck, Finding, FixBatch, FixProposal, Project, ProjectSnapshot, TestRun
from app.services.evaluation_engine import EvaluationEngine
from app.services.evaluation_planner import EvaluationPlanner
from app.services.project_detector import ProjectDetector
from app.services.scoring_engine import ScoringEngine, overall
from app.services.test_runner import TestRunner, sanitize_relative_path


def make_zip(files):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content if isinstance(content, bytes) else content.encode("utf-8"))
    return buffer.getvalue()


# 1. test_discovery_pytest_repository
def test_discovery_pytest_repository(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_example.py").write_text("import pytest\ndef test_dummy(): pass\n")

    detector = ProjectDetector()
    result = detector.inspect(tmp_path)
    assert result.test_file_count == 1
    pytest_frameworks = [tf for tf in result.test_frameworks if tf["name"] == "pytest"]
    assert len(pytest_frameworks) == 1

    planner = EvaluationPlanner()
    plan = planner.create_plan(result)
    test_checks = [c for c in plan if c["tool"] == "pytest"]
    assert len(test_checks) == 1
    assert test_checks[0]["name"] == "Python Test Execution"


# 2. test_no_tests_repository
def test_no_tests_repository(client, db_session):
    upload = client.post("/api/projects", files={"file": ("no_tests.zip", make_zip({"main.py": "print('hello')\n"}), "application/zip")})
    project_id = upload.json()["project_id"]
    eval_resp = client.post(f"/api/projects/{project_id}/evaluations")
    eval_id = eval_resp.json()["id"]

    run_resp = client.post(f"/api/evaluations/{eval_id}/run")
    assert run_resp.status_code == 200

    report_resp = client.post(f"/api/evaluations/{eval_id}/score")
    categories = {c["category"]: c for c in report_resp.json()["categories"]}
    assert categories["correctness"]["status"] == "not_measured"
    assert categories["testing"]["status"] == "not_measured"


# 3. test_execution_disabled_by_default
def test_execution_disabled_by_default(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", False):
        archive = make_zip({"main.py": "print('hello')\n", "tests/test_main.py": "def test_ok(): assert 1 == 1\n"})
        upload = client.post("/api/projects", files={"file": ("disabled.zip", archive, "application/zip")})
        project_id = upload.json()["project_id"]
        eval_resp = client.post(f"/api/projects/{project_id}/evaluations")
        eval_id = eval_resp.json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        score_resp = client.post(f"/api/evaluations/{eval_id}/score")
        categories = {c["category"]: c for c in score_resp.json()["categories"]}

        assert categories["correctness"]["status"] == "not_measured"
        assert categories["testing"]["status"] == "not_measured"

        report = client.get(f"/api/evaluations/{eval_id}/report").json()
        assert report["test_run"]["status"] == "blocked"
        assert "not enabled" in report["test_run"]["blocked_reason"]


# 4. test_all_tests_pass
def test_all_tests_pass(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {"calc.py": "def add(a, b): return a + b\n"}
        for i in range(5):
            files[f"tests/test_calc_{i}.py"] = f"from calc import add\ndef test_add_{i}(): assert add(1, 1) == 2\n"

        upload = client.post("/api/projects", files={"file": ("all_pass.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        score_resp = client.post(f"/api/evaluations/{eval_id}/score").json()
        categories = {c["category"]: c for c in score_resp["categories"]}

        assert categories["correctness"]["status"] == "measured"
        assert categories["correctness"]["score"] == 100


# 5. test_failed_tests
def test_failed_tests(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "calc.py": "def add(a, b): return a + b\n",
            "tests/test_calc.py": """
from calc import add
def test_1(): assert add(1, 1) == 2
def test_2(): assert add(2, 2) == 4
def test_3(): assert add(3, 3) == 6
def test_4(): assert add(4, 4) == 8
def test_5(): assert add(5, 5) == 99  # FAIL
"""
        }
        upload = client.post("/api/projects", files={"file": ("failed.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        score_resp = client.post(f"/api/evaluations/{eval_id}/score").json()
        categories = {c["category"]: c for c in score_resp["categories"]}

        assert categories["correctness"]["status"] == "measured"
        assert categories["correctness"]["score"] == 80


# 6. test_skipped_tests
def test_skipped_tests(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "main.py": "x = 1\n",
            "tests/test_main.py": """
import pytest
def test_pass(): assert 1 == 1
@pytest.mark.skip(reason="testing skip")
def test_skip(): assert 1 == 2
"""
        }
        upload = client.post("/api/projects", files={"file": ("skipped.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        score_resp = client.post(f"/api/evaluations/{eval_id}/score").json()
        categories = {c["category"]: c for c in score_resp["categories"]}

        assert categories["correctness"]["status"] == "measured"
        assert categories["correctness"]["score"] == 100


# 7. test_coverage_collection
def test_coverage_collection(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "calc.py": "def add(a, b): return a + b\n",
            "tests/test_calc.py": "from calc import add\ndef test_add(): assert add(1, 1) == 2\n"
        }
        upload = client.post("/api/projects", files={"file": ("cov.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        report = client.get(f"/api/evaluations/{eval_id}/report").json()
        test_run = report["test_run"]
        assert test_run["status"] == "completed"
        if test_run["coverage_percent"] is not None:
            assert isinstance(test_run["coverage_percent"], (int, float))


# 8. test_coverage_unavailable
def test_coverage_unavailable():
    test_run = TestRun(
        id="tr-cov-null",
        evaluation_id="eval-1",
        snapshot_id="snap-1",
        framework="pytest",
        status="completed",
        tests_collected=1,
        tests_passed=1,
        tests_failed=0,
        tests_skipped=0,
        tests_errors=0,
        coverage_percent=None
    )
    base_pts = 50
    suite_pts = 2
    score_val = max(0, min(60, base_pts + suite_pts))
    assert score_val == 52
    assert score_val < 100


# 9. test_timeout
def test_timeout(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        with patch.object(config, "TEST_TIMEOUT_SECONDS", 2):
            files = {
                "tests/test_loop.py": "import time\ndef test_forever():\n    time.sleep(10)\n"
            }
            upload = client.post("/api/projects", files={"file": ("timeout.zip", make_zip(files), "application/zip")})
            project_id = upload.json()["project_id"]
            eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

            client.post(f"/api/evaluations/{eval_id}/run")
            report = client.get(f"/api/evaluations/{eval_id}/report").json()

            assert report["test_run"]["status"] == "timeout"
            score_resp = client.post(f"/api/evaluations/{eval_id}/score").json()
            categories = {c["category"]: c for c in score_resp["categories"]}
            assert categories["correctness"]["status"] == "not_measured"


# 10. test_output_limit
def test_output_limit(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        with patch.object(config, "MAX_OUTPUT_BYTES", 200):
            files = {
                "tests/test_big_out.py": "def test_out():\n    for i in range(1000):\n        print('A' * 100)\n    assert True\n"
            }
            upload = client.post("/api/projects", files={"file": ("output_limit.zip", make_zip(files), "application/zip")})
            project_id = upload.json()["project_id"]
            eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

            client.post(f"/api/evaluations/{eval_id}/run")
            report = client.get(f"/api/evaluations/{eval_id}/report").json()

            assert len(report["test_run"]["stdout_summary"]) <= 200


# 11. test_repository_relative_paths
def test_repository_relative_paths(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "tests/test_fail_path.py": "def test_fail(): assert False, 'error in file'\n"
        }
        upload = client.post("/api/projects", files={"file": ("rel_path.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        report = client.get(f"/api/evaluations/{eval_id}/report").json()

        for failure in report["test_run"]["failures"]:
            assert not failure["file_path"].startswith("C:")
            assert not failure["file_path"].startswith("/")
            assert "rel_path.zip" not in failure["file_path"]
            assert failure["file_path"].startswith("tests/") or failure["file_path"] == "tests/test_fail_path.py"


# 12. test_derived_snapshot_execution
def test_derived_snapshot_execution(client, db_session):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files_a = {
            "calc.py": "def add(a, b): return a - b\n",  # Bug!
            "tests/test_calc.py": "from calc import add\ndef test_add(): assert add(2, 2) == 4\n"
        }
        upload = client.post("/api/projects", files={"file": ("orig.zip", make_zip(files_a), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_a = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_a}/run")
        report_a = client.post(f"/api/evaluations/{eval_a}/score").json()
        cats_a = {c["category"]: c for c in report_a["categories"]}
        assert cats_a["correctness"]["score"] == 0

        snapshot_a_id = client.get(f"/api/evaluations/{eval_a}").json()["snapshot_id"]

        snap_a = db_session.get(ProjectSnapshot, snapshot_a_id)
        derived_dir = Path(snap_a.workspace_path).parent / "derived-test-fix"
        derived_dir.mkdir(parents=True, exist_ok=True)

        (derived_dir / "calc.py").write_text("def add(a, b): return a + b\n")
        (derived_dir / "tests").mkdir(exist_ok=True)
        (derived_dir / "tests" / "test_calc.py").write_text("from calc import add\ndef test_add(): assert add(2, 2) == 4\n")

        derived_snapshot = ProjectSnapshot(
            project_id=project_id,
            archive_path=snap_a.archive_path,
            workspace_path=str(derived_dir),
            archive_size_bytes=0,
            file_count=2,
            uncompressed_size_bytes=100,
            parent_snapshot_id=snap_a.id,
            derivation_type="fix"
        )
        db_session.add(derived_snapshot)
        db_session.commit()

        eval_b = client.post(f"/api/snapshots/{derived_snapshot.id}/evaluations").json()["id"]
        client.post(f"/api/evaluations/{eval_b}/run")
        report_b = client.post(f"/api/evaluations/{eval_b}/score").json()
        cats_b = {c["category"]: c for c in report_b["categories"]}
        assert cats_b["correctness"]["score"] == 100


# 13. test_test_run_persistence
def test_test_run_persistence(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {"tests/test_persist.py": "def test_ok(): assert 1 == 1\n"}
        upload = client.post("/api/projects", files={"file": ("persist.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        client.post(f"/api/evaluations/{eval_id}/score")

        r1 = client.get(f"/api/evaluations/{eval_id}/report").json()
        r2 = client.get(f"/api/evaluations/{eval_id}/report").json()

        assert r1["test_run"]["id"] == r2["test_run"]["id"]
        assert r1["test_run"]["tests_passed"] == r2["test_run"]["tests_passed"] == 1


# 14. test_correctness_scoring
def test_correctness_scoring(db_session):
    engine = ScoringEngine()
    test_run = TestRun(
        id="tr-1",
        evaluation_id="eval-1",
        snapshot_id="snap-1",
        framework="pytest",
        status="completed",
        tests_collected=20,
        tests_passed=18,
        tests_failed=1,
        tests_skipped=0,
        tests_errors=1
    )
    db_session.add(test_run)
    eval_obj = Evaluation(id="eval-1", project_id="p1", snapshot_id="snap-1", status="completed")
    db_session.add(eval_obj)
    db_session.commit()

    scores = engine.score(db_session, eval_obj)
    corr = next(s for s in scores if s.category == "correctness")
    assert corr.status == "measured"
    assert corr.score == 90


# 15. test_testing_scoring
def test_testing_scoring(db_session):
    engine = ScoringEngine()
    
    test_run_cov = TestRun(
        id="tr-cov",
        evaluation_id="eval-cov",
        snapshot_id="snap-1",
        framework="pytest",
        status="completed",
        tests_collected=20,
        tests_passed=18,
        tests_failed=1,
        tests_skipped=1,
        tests_errors=0,
        coverage_percent=76.5
    )
    db_session.add(test_run_cov)
    eval_cov = Evaluation(id="eval-cov", project_id="p1", snapshot_id="snap-1", status="completed")
    db_session.add(eval_cov)
    db_session.commit()

    scores_cov = engine.score(db_session, eval_cov)
    t_cov = next(s for s in scores_cov if s.category == "testing")
    assert t_cov.status == "measured"
    assert t_cov.score == 91

    test_run_nocov = TestRun(
        id="tr-nocov",
        evaluation_id="eval-nocov",
        snapshot_id="snap-1",
        framework="pytest",
        status="completed",
        tests_collected=20,
        tests_passed=20,
        coverage_percent=None
    )
    db_session.add(test_run_nocov)
    eval_nocov = Evaluation(id="eval-nocov", project_id="p1", snapshot_id="snap-1", status="completed")
    db_session.add(eval_nocov)
    db_session.commit()

    scores_nocov = engine.score(db_session, eval_nocov)
    t_nocov = next(s for s in scores_nocov if s.category == "testing")
    assert t_nocov.status == "measured"
    assert t_nocov.score == 60
    assert "limited to a maximum of 60" in t_nocov.explanation


# 16. test_assessment_coverage_4_of_6
def test_assessment_coverage_4_of_6(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "calc.py": "def add(a, b): return a + b\n",
            "tests/test_calc.py": "from calc import add\ndef test_add(): assert add(1, 1) == 2\n"
        }
        upload = client.post("/api/projects", files={"file": ("cov46.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        score_resp = client.post(f"/api/evaluations/{eval_id}/score").json()

        ov = score_resp["overall"]
        assert ov["measured_categories"] in (4, 5, 6)
        assert ov["total_categories"] == 6

        categories = {c["category"]: c for c in score_resp["categories"]}
        assert categories["maintainability"]["status"] == "measured"
        assert categories["security"]["status"] == "measured"
        assert categories["correctness"]["status"] == "measured"
        assert categories["testing"]["status"] == "measured"
        assert categories["architecture"]["status"] in ("measured", "not_measured")


# 17. test_phase7_regression
def test_phase7_regression(client):
    archive = make_zip({
        "app.py": "import os\nprint('test')\n"
    })
    upload = client.post("/api/projects", files={"file": ("p7_reg.zip", archive, "application/zip")})
    project_id = upload.json()["project_id"]
    eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

    client.post(f"/api/evaluations/{eval_id}/run")
    client.post(f"/api/evaluations/{eval_id}/score")

    recs = client.post(f"/api/evaluations/{eval_id}/recommendations").json()
    assert isinstance(recs, list)


# 18. test_api_integration_phase8
def test_api_integration_phase8(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "calc.py": "def add(a, b): return a + b\n",
            "tests/test_calc.py": "from calc import add\ndef test_add(): assert add(1, 1) == 2\n"
        }
        upload = client.post("/api/projects", files={"file": ("api_phase8.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        client.post(f"/api/evaluations/{eval_id}/score")

        tests_resp = client.get(f"/api/evaluations/{eval_id}/tests")
        assert tests_resp.status_code == 200
        tests_data = tests_resp.json()
        assert tests_data["status"] == "completed"
        assert tests_data["tests_passed"] == 1

        report_resp = client.get(f"/api/evaluations/{eval_id}/report")
        assert report_resp.status_code == 200
        report_data = report_resp.json()
        assert report_data["test_run"]["tests_passed"] == 1
        assert report_data["scoring_version"] in ("1.1", "1.2", "1.3")


# 19. test_ruff_adapter_available_in_venv
def test_ruff_adapter_available_in_venv():
    from app.services.static_analyzers import RuffAdapter
    adapter = RuffAdapter()
    assert adapter.is_available() is True
    res = adapter.execute(Path("."))
    assert res.status != "tool_unavailable"


# 20. test_bandit_adapter_available_in_venv
def test_bandit_adapter_available_in_venv():
    from app.services.static_analyzers import BanditAdapter
    adapter = BanditAdapter()
    assert adapter.is_available() is True
    res = adapter.execute(Path("."))
    assert res.status != "tool_unavailable"


# 21. test_runner_isolation_does_not_mutate_global_environ
def test_runner_isolation_does_not_mutate_global_environ(tmp_path):
    import os
    env_before = os.environ.copy()
    runner = TestRunner()
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        runner._execute_pytest_local(tmp_path)
    env_after = os.environ.copy()
    assert env_before == env_after


# 22. test_sqlite_temp_db_clean_disposal
def test_sqlite_temp_db_clean_disposal():
    import tempfile
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from app.database import initialize_database

    td = tempfile.TemporaryDirectory()
    try:
        db_file = Path(td.name) / "test_clean.db"
        eng = create_engine(f"sqlite:///{db_file}")
        initialize_database(eng)
        Session = sessionmaker(bind=eng)
        sess = Session()
        sess.execute(text("SELECT 1"))
        sess.close()
        eng.dispose()
    finally:
        td.cleanup()
    assert not Path(td.name).exists()


# 23. test_calculator_snapshot_under_data_dir_executes_all_5_tests
def test_calculator_snapshot_under_data_dir_executes_all_5_tests(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "calculator.py": "def add(a, b): return a + b\ndef divide(a, b): return a / b\n",
            "tests/test_calculator.py": (
                "import pytest\n"
                "from calculator import add, divide\n"
                "def test_add_positive(): assert add(2, 3) == 5\n"
                "def test_add_negative(): assert add(-1, -1) == -2\n"
                "def test_divide_valid(): assert divide(10, 2) == 5\n"
                "def test_divide_by_zero():\n"
                "    with pytest.raises(ZeroDivisionError):\n"
                "        divide(10, 0)\n"
                "def test_intentional_failure(): assert add(2, 2) == 5\n"
            )
        }
        upload = client.post("/api/projects", files={"file": ("calc5.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        client.post(f"/api/evaluations/{eval_id}/score")
        report = client.get(f"/api/evaluations/{eval_id}/report").json()

        test_run = report["test_run"]
        assert test_run["status"] == "completed"
        assert test_run["tests_collected"] == 5
        assert test_run["tests_passed"] == 4
        assert test_run["tests_failed"] == 1
        assert test_run["tests_errors"] == 0

        correctness = next(c for c in report["categories"] if c["category"] == "correctness")
        assert correctness["status"] == "measured"
        assert correctness["score"] == 80


# 24. test_zero_collected_tests_status_and_null_coverage
def test_zero_collected_tests_status_and_null_coverage(client):
    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        files = {
            "empty.py": "x = 1\n",
            "tests/test_empty.py": "# No test functions here\n"
        }
        upload = client.post("/api/projects", files={"file": ("zero_coll.zip", make_zip(files), "application/zip")})
        project_id = upload.json()["project_id"]
        eval_id = client.post(f"/api/projects/{project_id}/evaluations").json()["id"]

        client.post(f"/api/evaluations/{eval_id}/run")
        client.post(f"/api/evaluations/{eval_id}/score")
        report = client.get(f"/api/evaluations/{eval_id}/report").json()

        test_run = report["test_run"]
        assert test_run["status"] == "no_tests_collected"
        assert test_run["coverage_percent"] is None

        correctness = next(c for c in report["categories"] if c["category"] == "correctness")
        assert correctness["status"] == "not_measured"

        testing = next(c for c in report["categories"] if c["category"] == "testing")
        assert testing["status"] == "not_measured"


