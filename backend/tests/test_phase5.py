import hashlib
from pathlib import Path
import pytest
from fastapi import HTTPException

from app.models import CategoryScore, Evaluation, Finding, Project, ProjectSnapshot, Recommendation, FixProposal
from app.services.recommendation_engine import RecommendationEngine, safe_file, digest


def setup_evaluation(db_session, tmp_path, rules=("F401",)):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "app.py"
    source.write_text("import os\nimport subprocess\n\nprint('ok')\n", encoding="utf-8")
    
    project = Project(name="phase5", status="uploaded")
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
    
    for index, rule in enumerate(rules):
        category = "maintainability" if rule == "F401" else "security"
        tool = "ruff" if rule == "F401" else "bandit"
        line_start = 1 if rule == "F401" else 2
        message = "`os` imported but unused" if rule == "F401" else f"Evidence for {rule}"
        db_session.add(
            Finding(
                evaluation_id=evaluation.id,
                check_id=f"check-{index}",
                category=category,
                tool=tool,
                rule_id=rule,
                severity="low",
                title=f"Rule {rule}",
                message=message,
                file_path="app.py",
                line_start=line_start,
                fingerprint=f"fingerprint-{rule}-{index}",
            )
        )
    db_session.commit()
    return evaluation, snapshot, source


def test_recommendations_rule_coverage(db_session, tmp_path):
    rules = ("F401", "B105", "B404", "B602", "B607", "UNKNOWN_RULE")
    evaluation, _, source = setup_evaluation(db_session, tmp_path, rules)
    
    engine = RecommendationEngine()
    recommendations = engine.generate(db_session, evaluation)
    
    assert len(recommendations) == 6
    recs_by_rule = {r.rule_id: r for r in recommendations}
    
    # F401
    f401_rec = recs_by_rule["F401"]
    f401_finding = db_session.query(Finding).filter_by(evaluation_id=evaluation.id, rule_id="F401").first()
    assert f401_rec.finding_id == f401_finding.id
    assert f401_rec.fixability == "automatic"
    assert f401_rec.tool == "ruff"
    assert f401_rec.category == "maintainability"
    assert f401_rec.title == "Unused import"
    assert "unused import" in f401_rec.recommended_action.lower()
    
    # Manual Bandit rules
    for manual_rule in ("B105", "B404", "B602", "B607"):
        assert recs_by_rule[manual_rule].fixability == "manual"
        assert recs_by_rule[manual_rule].tool == "bandit"
        assert recs_by_rule[manual_rule].category == "security"
        
    # Unknown rule
    unknown_rec = recs_by_rule["UNKNOWN_RULE"]
    assert unknown_rec.fixability == "unsupported"
    assert unknown_rec.title == "Manual review recommended"
    
    # Source file remains untouched
    assert source.read_text(encoding="utf-8").startswith("import os")


def test_recommendation_idempotency(db_session, tmp_path):
    evaluation, _, _ = setup_evaluation(db_session, tmp_path, ("F401", "B105"))
    engine = RecommendationEngine()
    
    first_run = engine.generate(db_session, evaluation)
    first_tuples = sorted((r.finding_id, r.rule_id, r.fixability) for r in first_run)
    
    second_run = engine.generate(db_session, evaluation)
    second_tuples = sorted((r.finding_id, r.rule_id, r.fixability) for r in second_run)
    
    assert first_tuples == second_tuples
    assert db_session.query(Recommendation).filter_by(evaluation_id=evaluation.id).count() == 2


def test_f401_preview(db_session, tmp_path):
    evaluation, snapshot, source = setup_evaluation(db_session, tmp_path)
    engine = RecommendationEngine()
    
    recommendation = engine.generate(db_session, evaluation)[0]
    proposal = engine.preview(db_session, recommendation, evaluation)
    
    # Verification
    assert source.read_text(encoding="utf-8") == "import os\nimport subprocess\n\nprint('ok')\n"
    assert proposal.recommendation_id == recommendation.id
    assert proposal.file_path == "app.py"
    assert proposal.original_content_hash == digest("import os\nimport subprocess\n\nprint('ok')\n")
    assert proposal.proposed_content == "import subprocess\n\nprint('ok')\n"
    assert "import subprocess" in proposal.proposed_content
    assert "import os" not in proposal.proposed_content
    assert "-import os" in proposal.diff
    assert proposal.status == "proposed"
    
    # Verify preview did NOT create a derived snapshot
    snapshots = db_session.query(ProjectSnapshot).filter_by(project_id=evaluation.project_id).all()
    assert len(snapshots) == 1


def test_apply_fix(db_session, tmp_path):
    evaluation, original_snapshot, source = setup_evaluation(db_session, tmp_path)
    engine = RecommendationEngine()
    
    recommendation = engine.generate(db_session, evaluation)[0]
    proposal = engine.preview(db_session, recommendation, evaluation)
    
    from app.api.routes import apply_fix
    result = apply_fix(proposal.id, db_session)
    
    # ORIGINAL SNAPSHOT Verification
    assert source.read_text(encoding="utf-8") == "import os\nimport subprocess\n\nprint('ok')\n"
    
    # DERIVED SNAPSHOT Verification
    derived = db_session.get(ProjectSnapshot, result["derived_snapshot_id"])
    assert derived is not None
    assert derived.parent_snapshot_id == original_snapshot.id
    assert derived.derivation_type == "fix"
    assert derived.workspace_path != original_snapshot.workspace_path
    
    derived_file = Path(derived.workspace_path) / "app.py"
    assert derived_file.read_text(encoding="utf-8") == "import subprocess\n\nprint('ok')\n"
    
    # FIX PROPOSAL Verification
    proposal_in_db = db_session.get(FixProposal, proposal.id)
    assert proposal_in_db.status == "applied"
    assert result["status"] == "applied"
    assert "verification pending" in result["message"].lower()


def test_explicit_approval_boundary(db_session, tmp_path):
    evaluation, original_snapshot, source = setup_evaluation(db_session, tmp_path)
    engine = RecommendationEngine()
    
    # 1. Generating recommendation does NOT modify code or create snapshots
    recommendation = engine.generate(db_session, evaluation)[0]
    assert db_session.query(ProjectSnapshot).filter_by(project_id=evaluation.project_id).count() == 1
    assert source.read_text(encoding="utf-8").startswith("import os")
    
    # 2. Generating preview does NOT modify code or create snapshots
    proposal = engine.preview(db_session, recommendation, evaluation)
    assert db_session.query(ProjectSnapshot).filter_by(project_id=evaluation.project_id).count() == 1
    assert source.read_text(encoding="utf-8").startswith("import os")
    
    # 3. ONLY explicit Apply creates modified derived copy
    from app.api.routes import apply_fix
    apply_fix(proposal.id, db_session)
    assert db_session.query(ProjectSnapshot).filter_by(project_id=evaluation.project_id).count() == 2
    assert source.read_text(encoding="utf-8").startswith("import os")


def test_manual_findings_cannot_auto_apply(db_session, tmp_path):
    evaluation, _, source = setup_evaluation(db_session, tmp_path, ("B602", "B105"))
    engine = RecommendationEngine()
    
    recs = engine.generate(db_session, evaluation)
    assert len(recs) == 2
    
    for rec in recs:
        with pytest.raises(ValueError) as exc:
            engine.preview(db_session, rec, evaluation)
        assert "manual fix" in str(exc.value).lower()
        
    assert db_session.query(FixProposal).filter_by(evaluation_id=evaluation.id).count() == 0
    assert db_session.query(ProjectSnapshot).filter_by(project_id=evaluation.project_id).count() == 1
    assert source.read_text(encoding="utf-8").startswith("import os")


@pytest.mark.parametrize("unsafe", ["../outside.py", "..\\outside.py"])
def test_path_traversal_security(db_session, tmp_path, unsafe):
    with pytest.raises(ValueError) as exc:
        safe_file(str(tmp_path), unsafe)
    assert "unsafe" in str(exc.value).lower()


def test_absolute_path_security(db_session, tmp_path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("external content", encoding="utf-8")
    
    with pytest.raises(ValueError) as exc:
        safe_file(str(tmp_path), str(outside))
    assert "unsafe" in str(exc.value).lower()
    assert outside.read_text(encoding="utf-8") == "external content"


def test_symlink_safety(db_session, tmp_path):
    outside = tmp_path.parent / "outside_target.py"
    outside.write_text("outside data", encoding="utf-8")
    
    link = tmp_path / "link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is not permitted in this environment.")
        
    with pytest.raises(ValueError) as exc:
        safe_file(str(tmp_path), "link.py")
    assert "unsafe" in str(exc.value).lower()


def test_stale_preview(db_session, tmp_path):
    evaluation, _, source = setup_evaluation(db_session, tmp_path)
    engine = RecommendationEngine()
    
    recommendation = engine.generate(db_session, evaluation)[0]
    proposal = engine.preview(db_session, recommendation, evaluation)
    
    # Mutate original file before apply
    source.write_text("import os\n# user edited file\nimport subprocess\n", encoding="utf-8")
    
    from fastapi import HTTPException
    from app.api.routes import apply_fix
    
    with pytest.raises(HTTPException) as exc:
        apply_fix(proposal.id, db_session)
        
    assert exc.value.status_code == 409
    assert "source changed" in exc.value.detail.lower()
    assert db_session.query(ProjectSnapshot).filter_by(project_id=evaluation.project_id).count() == 1


def test_diff_correctness(db_session, tmp_path):
    evaluation, _, _ = setup_evaluation(db_session, tmp_path)
    engine = RecommendationEngine()
    
    recommendation = engine.generate(db_session, evaluation)[0]
    proposal = engine.preview(db_session, recommendation, evaluation)
    
    lines = proposal.diff.splitlines()
    assert any("--- app.py" in line for line in lines)
    assert any("+++ app.py" in line for line in lines)
    assert any("-import os" in line for line in lines)


def test_no_phase6_side_effects(db_session, tmp_path):
    evaluation, _, _ = setup_evaluation(db_session, tmp_path)
    engine = RecommendationEngine()
    
    recommendation = engine.generate(db_session, evaluation)[0]
    proposal = engine.preview(db_session, recommendation, evaluation)
    
    initial_eval_count = db_session.query(Evaluation).filter_by(project_id=evaluation.project_id).count()
    initial_score_count = db_session.query(CategoryScore).filter_by(evaluation_id=evaluation.id).count()
    
    from app.api.routes import apply_fix
    result = apply_fix(proposal.id, db_session)
    
    assert db_session.query(Evaluation).filter_by(project_id=evaluation.project_id).count() == initial_eval_count
    assert db_session.query(CategoryScore).filter_by(evaluation_id=evaluation.id).count() == initial_score_count
    assert "verification pending" in result["message"].lower()


def test_api_endpoints_integration(client, db_session, tmp_path):
    evaluation, _, _ = setup_evaluation(db_session, tmp_path)
    
    # 1. Generate recommendations
    res = client.post(f"/api/evaluations/{evaluation.id}/recommendations")
    assert res.status_code == 200
    recs = res.json()
    assert len(recs) == 1
    rec_id = recs[0]["id"]
    
    # 2. Get recommendations
    res = client.get(f"/api/evaluations/{evaluation.id}/recommendations")
    assert res.status_code == 200
    assert len(res.json()) == 1
    
    # 3. Preview fix
    res = client.post(f"/api/recommendations/{rec_id}/preview")
    assert res.status_code == 200
    proposal = res.json()
    assert proposal["file_path"] == "app.py"
    assert "id" in proposal
    fix_id = proposal["id"]
    
    # 4. Apply fix
    res = client.post(f"/api/fixes/{fix_id}/apply")
    assert res.status_code == 200
    applied = res.json()
    assert applied["status"] == "applied"
    assert "derived_snapshot_id" in applied


def test_real_integration_f401_preview_shape(db_session, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_content = (
        "import os\n"
        "import subprocess\n"
        "\n"
        'DEMO_PASSWORD = "codeeval-demo-password-not-a-real-secret"\n'
        "\n"
        "def static_analysis_example():\n"
        '    subprocess.run("echo static-analysis-only", shell=True, check=False)\n'
        "    return DEMO_PASSWORD\n"
    )
    source = tmp_path / "app.py"
    source.write_text(source_content, encoding="utf-8")

    project = Project(name="real-demo", status="uploaded")
    db_session.add(project)
    db_session.flush()

    snapshot = ProjectSnapshot(
        project_id=project.id,
        archive_path="archive.zip",
        workspace_path=str(tmp_path),
        archive_size_bytes=len(source_content),
        file_count=1,
        uncompressed_size_bytes=len(source_content),
    )
    db_session.add(snapshot)
    db_session.flush()

    evaluation = Evaluation(project_id=project.id, snapshot_id=snapshot.id, status="completed")
    db_session.add(evaluation)
    db_session.flush()

    db_session.add(
        Finding(
            evaluation_id=evaluation.id,
            check_id="ruff-check",
            category="maintainability",
            tool="ruff",
            rule_id="F401",
            severity="low",
            title="F401",
            message="`os` imported but unused",
            file_path="app.py",
            line_start=1,
            fingerprint="fingerprint-f401-real",
        )
    )
    db_session.commit()

    engine = RecommendationEngine()
    recommendations = engine.generate(db_session, evaluation)
    assert len(recommendations) == 1
    rec = recommendations[0]
    assert rec.fixability == "automatic"

    proposal = engine.preview(db_session, rec, evaluation)
    assert proposal is not None

    # Verification:
    # 1. Original file remains unchanged
    assert source.read_text(encoding="utf-8") == source_content

    # 2. Proposed content removes only `import os` and preserves `import subprocess` and all unrelated code
    expected_proposed = (
        "import subprocess\n"
        "\n"
        'DEMO_PASSWORD = "codeeval-demo-password-not-a-real-secret"\n'
        "\n"
        "def static_analysis_example():\n"
        '    subprocess.run("echo static-analysis-only", shell=True, check=False)\n'
        "    return DEMO_PASSWORD\n"
    )
    assert proposal.proposed_content == expected_proposed
    assert "import subprocess" in proposal.proposed_content
    assert "DEMO_PASSWORD" in proposal.proposed_content


def test_f401_preview_with_utf8_bom(db_session, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "app.py"
    source.write_bytes("\ufeffimport os\nimport subprocess\n".encode("utf-8"))

    project = Project(name="bom-demo", status="uploaded")
    db_session.add(project)
    db_session.flush()

    snapshot = ProjectSnapshot(
        project_id=project.id,
        archive_path="archive.zip",
        workspace_path=str(tmp_path),
        archive_size_bytes=100,
        file_count=1,
        uncompressed_size_bytes=100,
    )
    db_session.add(snapshot)
    db_session.flush()

    evaluation = Evaluation(project_id=project.id, snapshot_id=snapshot.id, status="completed")
    db_session.add(evaluation)
    db_session.flush()

    db_session.add(
        Finding(
            evaluation_id=evaluation.id,
            check_id="ruff-check",
            category="maintainability",
            tool="ruff",
            rule_id="F401",
            severity="low",
            title="F401",
            message="`os` imported but unused",
            file_path="app.py",
            line_start=1,
            fingerprint="fingerprint-f401-bom",
        )
    )
    db_session.commit()

    engine = RecommendationEngine()
    recommendation = engine.generate(db_session, evaluation)[0]
    proposal = engine.preview(db_session, recommendation, evaluation)
    assert proposal.proposed_content == "import subprocess\n"


def test_preview_rejected_when_source_line_not_import(db_session, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "app.py"
    source.write_text("print('hello')\nimport subprocess\n", encoding="utf-8")

    project = Project(name="bad-line", status="uploaded")
    db_session.add(project)
    db_session.flush()

    snapshot = ProjectSnapshot(
        project_id=project.id,
        archive_path="archive.zip",
        workspace_path=str(tmp_path),
        archive_size_bytes=100,
        file_count=1,
        uncompressed_size_bytes=100,
    )
    db_session.add(snapshot)
    db_session.flush()

    evaluation = Evaluation(project_id=project.id, snapshot_id=snapshot.id, status="completed")
    db_session.add(evaluation)
    db_session.flush()

    db_session.add(
        Finding(
            evaluation_id=evaluation.id,
            check_id="ruff-check",
            category="maintainability",
            tool="ruff",
            rule_id="F401",
            severity="low",
            title="F401",
            message="`os` imported but unused",
            file_path="app.py",
            line_start=1,
            fingerprint="fingerprint-f401-bad-line",
        )
    )
    db_session.commit()

    engine = RecommendationEngine()
    recommendation = engine.generate(db_session, evaluation)[0]
    with pytest.raises(ValueError) as exc:
        engine.preview(db_session, recommendation, evaluation)
    assert "source changed" in str(exc.value).lower()
