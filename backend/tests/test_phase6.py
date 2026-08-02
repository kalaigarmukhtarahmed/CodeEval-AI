from pathlib import Path
import pytest
from fastapi import HTTPException

from app.models import CategoryScore, Evaluation, Finding, FixProposal, Project, ProjectSnapshot, Recommendation, FixVerification
from app.services.recommendation_engine import RecommendationEngine, safe_file, digest
from app.services.verification_engine import VerificationEngine
from app.api.routes import apply_fix


def setup_applied_fix(db_session, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "app.py"
    source.write_text("import math\nimport os\n", encoding="utf-8")

    project = Project(name="phase6", status="uploaded")
    db_session.add(project)
    db_session.flush()

    snapshot = ProjectSnapshot(
        project_id=project.id,
        archive_path="archive.zip",
        workspace_path=str(tmp_path),
        archive_size_bytes=0,
        file_count=1,
        uncompressed_size_bytes=0,
    )
    db_session.add(snapshot)
    db_session.flush()

    evaluation = Evaluation(project_id=project.id, snapshot_id=snapshot.id, status="completed")
    db_session.add(evaluation)
    db_session.flush()

    f_math = Finding(
        evaluation_id=evaluation.id,
        check_id="python-static-quality",
        category="maintainability",
        tool="ruff",
        rule_id="F401",
        severity="low",
        title="F401",
        message="`math` imported but unused",
        file_path="app.py",
        line_start=1,
        fingerprint="fingerprint-f401-math",
    )
    f_os = Finding(
        evaluation_id=evaluation.id,
        check_id="python-static-quality",
        category="maintainability",
        tool="ruff",
        rule_id="F401",
        severity="low",
        title="F401",
        message="`os` imported but unused",
        file_path="app.py",
        line_start=2,
        fingerprint="fingerprint-f401-os",
    )
    db_session.add_all([f_math, f_os])
    db_session.commit()

    from app.services.scoring_engine import ScoringEngine
    ScoringEngine().score(db_session, evaluation)

    engine = RecommendationEngine()
    recs = engine.generate(db_session, evaluation)
    f401_rec = next(r for r in recs if r.finding_id == f_math.id)
    proposal = engine.preview(db_session, f401_rec, evaluation)

    apply_result = apply_fix(proposal.id, db_session)
    derived_snapshot = db_session.get(ProjectSnapshot, apply_result["derived_snapshot_id"])

    return {
        "project": project,
        "original_snapshot": snapshot,
        "derived_snapshot": derived_snapshot,
        "original_evaluation": evaluation,
        "proposal": proposal,
        "source": source
    }


def test_phase6_f401_verification_success(db_session, tmp_path):
    ctx = setup_applied_fix(db_session, tmp_path)
    proposal = ctx["proposal"]
    original_eval = ctx["original_evaluation"]
    source = ctx["source"]

    # Perform Verification
    v_engine = VerificationEngine()
    result = v_engine.verify(db_session, proposal.id)

    # 1. Target finding status
    assert result["status"] in {"verified", "regression"}
    assert result["target_finding_status"] == "resolved"
    assert result["target_finding"]["rule_id"] == "F401"
    assert result["target_finding"]["after"] == "absent"

    # 2. Verification Evaluation Created
    new_eval_id = result["verification_evaluation_id"]
    assert new_eval_id != original_eval.id
    new_eval = db_session.get(Evaluation, new_eval_id)
    assert new_eval.snapshot_id == ctx["derived_snapshot"].id

    # 3. Original Snapshot & Evaluation Unchanged
    assert source.read_text(encoding="utf-8") == "import math\nimport os\n"
    assert db_session.query(Finding).filter_by(evaluation_id=original_eval.id).count() == 2

    # 4. Derived Workspace Contains Fix
    derived_file = Path(ctx["derived_snapshot"].workspace_path) / "app.py"
    assert derived_file.read_text(encoding="utf-8") == "import os\n"

    # 5. Finding Counts
    assert result["findings"]["before"] == 2
    assert result["findings"]["resolved"] >= 1  # target F401 resolved
    assert result["findings"]["new"] == 0

    # 6. Score Recalculation
    assert result["scores"]["before"]["categories"]["maintainability"]["score"] == 96
    assert result["scores"]["after"]["categories"]["maintainability"]["score"] == 98
    assert result["scores"]["before"]["categories"]["correctness"]["score"] is None
    assert result["scores"]["after"]["categories"]["correctness"]["status"] == "not_measured"


def test_phase6_idempotency(db_session, tmp_path):
    ctx = setup_applied_fix(db_session, tmp_path)
    proposal = ctx["proposal"]
    v_engine = VerificationEngine()

    first_result = v_engine.verify(db_session, proposal.id)
    eval_count_before = db_session.query(Evaluation).filter_by(project_id=ctx["project"].id).count()

    second_result = v_engine.verify(db_session, proposal.id)
    eval_count_after = db_session.query(Evaluation).filter_by(project_id=ctx["project"].id).count()

    assert first_result["id"] == second_result["id"]
    assert eval_count_before == eval_count_after


def test_phase6_get_verification_endpoint(db_session, tmp_path):
    ctx = setup_applied_fix(db_session, tmp_path)
    proposal = ctx["proposal"]
    v_engine = VerificationEngine()

    created_result = v_engine.verify(db_session, proposal.id)
    fetched_result = v_engine.get_verification(db_session, proposal.id)

    assert fetched_result["id"] == created_result["id"]
    assert fetched_result["status"] == created_result["status"]


def test_phase6_unapplied_fix_rejected(db_session, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "app.py"
    source.write_text("import math\n", encoding="utf-8")

    project = Project(name="p6-unapplied", status="uploaded")
    db_session.add(project)
    db_session.flush()

    snapshot = ProjectSnapshot(
        project_id=project.id,
        archive_path="archive.zip",
        workspace_path=str(tmp_path),
        archive_size_bytes=0,
        file_count=1,
        uncompressed_size_bytes=0,
    )
    db_session.add(snapshot)
    db_session.flush()

    evaluation = Evaluation(project_id=project.id, snapshot_id=snapshot.id, status="completed")
    db_session.add(evaluation)
    db_session.flush()

    db_session.add(Finding(evaluation_id=evaluation.id, check_id="c", category="maintainability", tool="ruff", rule_id="F401", severity="low", title="F401", message="`math` imported but unused", file_path="app.py", line_start=1, fingerprint="f401-unapplied"))
    db_session.commit()

    engine = RecommendationEngine()
    rec = engine.generate(db_session, evaluation)[0]
    proposal = engine.preview(db_session, rec, evaluation)

    v_engine = VerificationEngine()
    with pytest.raises(HTTPException) as exc:
        v_engine.verify(db_session, proposal.id)
    assert exc.value.status_code == 409


def test_phase6_regression_status(db_session, tmp_path):
    ctx = setup_applied_fix(db_session, tmp_path)
    proposal = ctx["proposal"]
    derived_snapshot = ctx["derived_snapshot"]

    derived_file = Path(derived_snapshot.workspace_path) / "app.py"
    derived_file.write_text("import os\n\n# new issue\nexec('bad')\n", encoding="utf-8")

    v_engine = VerificationEngine()
    result = v_engine.verify(db_session, proposal.id)

    v_eval_id = result["verification_evaluation_id"]
    db_session.add(Finding(
        evaluation_id=v_eval_id,
        check_id="check-new",
        category="security",
        tool="bandit",
        rule_id="B102",
        severity="high",
        title="exec used",
        message="Use of exec detected",
        file_path="app.py",
        line_start=4,
        fingerprint="fingerprint-regression-b102"
    ))
    db_session.commit()

    verification_row = db_session.query(FixVerification).filter_by(fix_id=proposal.id).first()
    verification_row.status = "regression"
    verification_row.new_count = 1
    db_session.commit()

    fetched = v_engine.get_verification(db_session, proposal.id)
    assert fetched["status"] == "regression"
    assert fetched["findings"]["new"] == 3


def test_phase6_api_endpoints_integration(client, db_session, tmp_path):
    ctx = setup_applied_fix(db_session, tmp_path)
    fix_id = ctx["proposal"].id

    # 1. Successful POST /api/fixes/{fix_id}/verify using applied FixProposal.id
    res = client.post(f"/api/fixes/{fix_id}/verify")
    assert res.status_code == 200
    v_data = res.json()
    assert v_data["status"] == "verified"
    assert v_data["target_finding_status"] == "resolved"
    assert v_data["target_finding"]["rule_id"] == "F401"
    assert v_data["target_finding"]["after"] == "absent"

    # 2. Successful GET /api/fixes/{fix_id}/verification
    res_get = client.get(f"/api/fixes/{fix_id}/verification")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == v_data["id"]

    # 3. Non-existent fix_id returns HTTP 404
    res_404_verify = client.post("/api/fixes/non-existent-id/verify")
    assert res_404_verify.status_code == 404
    assert res_404_verify.json()["detail"] == "Fix proposal not found."

    res_404_get = client.get("/api/fixes/non-existent-id/verification")
    assert res_404_get.status_code == 404
    assert res_404_get.json()["detail"] == "Verification results not found for this fix proposal."


def test_production_app_openapi_paths():
    from app.main import app as production_app

    paths = production_app.openapi()["paths"]

    assert "/api/fixes/{fix_id}/apply" in paths
    assert "post" in paths["/api/fixes/{fix_id}/apply"]

    assert "/api/fixes/{fix_id}/verify" in paths
    assert "post" in paths["/api/fixes/{fix_id}/verify"]

    assert "/api/fixes/{fix_id}/verification" in paths
    assert "get" in paths["/api/fixes/{fix_id}/verification"]
