from pathlib import Path
import pytest
from fastapi import HTTPException

from app.models import CategoryScore, Evaluation, Finding, FixBatch, FixProposal, Project, ProjectSnapshot, Recommendation, FixVerification
from app.services.recommendation_engine import RecommendationEngine, safe_file, digest
from app.services.verification_engine import VerificationEngine
from app.api.routes import apply_fix, apply_batch


def setup_multi_fix_repo(db_session, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    f1 = tmp_path / "app.py"
    f1.write_text("import math\nimport os\n\nprint('hello')\n", encoding="utf-8")

    f2 = tmp_path / "utils.py"
    f2.write_text("import sys\nimport re\n\ndef helper():\n    return 42\n", encoding="utf-8")

    project = Project(name="phase7", status="uploaded")
    db_session.add(project)
    db_session.flush()

    snapshot = ProjectSnapshot(
        project_id=project.id,
        archive_path="archive.zip",
        workspace_path=str(tmp_path),
        archive_size_bytes=0,
        file_count=2,
        uncompressed_size_bytes=0,
    )
    db_session.add(snapshot)
    db_session.flush()

    evaluation = Evaluation(project_id=project.id, snapshot_id=snapshot.id, status="completed")
    db_session.add(evaluation)
    db_session.flush()

    # Findings
    f_math = Finding(
        evaluation_id=evaluation.id, check_id="python-static-quality", category="maintainability",
        tool="ruff", rule_id="F401", severity="low", title="F401", message="`math` imported but unused",
        file_path="app.py", line_start=1, fingerprint="fp-f401-math"
    )
    f_os = Finding(
        evaluation_id=evaluation.id, check_id="python-static-quality", category="maintainability",
        tool="ruff", rule_id="F401", severity="low", title="F401", message="`os` imported but unused",
        file_path="app.py", line_start=2, fingerprint="fp-f401-os"
    )
    f_sys = Finding(
        evaluation_id=evaluation.id, check_id="python-static-quality", category="maintainability",
        tool="ruff", rule_id="F401", severity="low", title="F401", message="`sys` imported but unused",
        file_path="utils.py", line_start=1, fingerprint="fp-f401-sys"
    )
    f_manual = Finding(
        evaluation_id=evaluation.id, check_id="python-security", category="security",
        tool="bandit", rule_id="B105", severity="medium", title="B105", message="Hardcoded password",
        file_path="app.py", line_start=4, fingerprint="fp-b105"
    )

    db_session.add_all([f_math, f_os, f_sys, f_manual])
    db_session.commit()

    from app.services.scoring_engine import ScoringEngine
    ScoringEngine().score(db_session, evaluation)

    engine = RecommendationEngine()
    recs = engine.generate(db_session, evaluation)

    return {
        "project": project,
        "snapshot": snapshot,
        "evaluation": evaluation,
        "recs": recs,
        "f1": f1,
        "f2": f2,
        "f_math": f_math,
        "f_os": f_os,
        "f_sys": f_sys,
        "f_manual": f_manual
    }


def test_1_2_3_batch_preview_multi_file(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    auto_recs = [r for r in ctx["recs"] if r.fixability == "automatic"]
    rec_ids = [r.id for r in auto_recs]

    batch = engine.preview_batch(db_session, ctx["evaluation"].id, rec_ids)

    assert batch.fix_count == 3
    assert batch.files_changed_count == 2
    assert batch.status == "proposed"
    assert "app.py" in batch.combined_diff
    assert "utils.py" in batch.combined_diff

    # Verify preview does not modify source snapshot (Req 11 & 14)
    assert ctx["f1"].read_text(encoding="utf-8") == "import math\nimport os\n\nprint('hello')\n"
    assert ctx["f2"].read_text(encoding="utf-8") == "import sys\nimport re\n\ndef helper():\n    return 42\n"


def test_4_manual_recommendation_rejected(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    manual_rec = next(r for r in ctx["recs"] if r.fixability == "manual")

    with pytest.raises(HTTPException) as exc:
        engine.preview_batch(db_session, ctx["evaluation"].id, [manual_rec.id])
    assert exc.value.status_code == 409


def test_5_recommendation_from_another_evaluation_rejected(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    # Create another evaluation
    other_eval = Evaluation(project_id=ctx["project"].id, snapshot_id=ctx["snapshot"].id, status="completed")
    db_session.add(other_eval)
    db_session.flush()

    other_rec = Recommendation(
        evaluation_id=other_eval.id, finding_id="f", category="m", tool="ruff", rule_id="F401",
        title="t", description="d", why_it_matters="w", recommended_action="a", fixability="automatic",
        generation_method="g", status="generated"
    )
    db_session.add(other_rec)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        engine.preview_batch(db_session, ctx["evaluation"].id, [other_rec.id])
    assert exc.value.status_code == 404


def test_6_missing_recommendation_rejected(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    with pytest.raises(HTTPException) as exc:
        engine.preview_batch(db_session, ctx["evaluation"].id, ["missing-rec-id"])
    assert exc.value.status_code == 404


def test_7_conflicting_transformations_rejected(db_session, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    f1 = tmp_path / "app.py"
    f1.write_text("import math\n", encoding="utf-8")

    project = Project(name="p-conflict", status="uploaded")
    db_session.add(project)
    db_session.flush()

    snapshot = ProjectSnapshot(project_id=project.id, archive_path="a.zip", workspace_path=str(tmp_path), archive_size_bytes=0, file_count=1, uncompressed_size_bytes=0)
    db_session.add(snapshot)
    db_session.flush()

    evaluation = Evaluation(project_id=project.id, snapshot_id=snapshot.id, status="completed")
    db_session.add(evaluation)
    db_session.flush()

    # Two findings targeting exact same line start=1
    f1_finding = Finding(evaluation_id=evaluation.id, check_id="c", category="maintainability", tool="ruff", rule_id="F401", severity="low", title="t", message="`math` imported but unused", file_path="app.py", line_start=1, fingerprint="fp1")
    f2_finding = Finding(evaluation_id=evaluation.id, check_id="c", category="maintainability", tool="ruff", rule_id="F401", severity="low", title="t", message="`math` imported but unused", file_path="app.py", line_start=1, fingerprint="fp2")
    db_session.add_all([f1_finding, f2_finding])
    db_session.commit()

    engine = RecommendationEngine()
    recs = engine.generate(db_session, evaluation)
    rec_ids = [r.id for r in recs]

    with pytest.raises(HTTPException) as exc:
        engine.preview_batch(db_session, evaluation.id, rec_ids)
    assert exc.value.status_code == 409
    assert "conflicting" in exc.value.detail.lower()


def test_8_9_path_security_validation():
    with pytest.raises(ValueError):
        safe_file("/workspace", "../outside.py")
    with pytest.raises(ValueError):
        safe_file("/workspace", "/etc/passwd")


def test_12_13_14_15_batch_apply_lineage(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    auto_recs = [r for r in ctx["recs"] if r.fixability == "automatic" and r.rule_id == "F401"]
    rec_ids = [r.id for r in auto_recs]

    batch = engine.preview_batch(db_session, ctx["evaluation"].id, rec_ids)
    apply_res = engine.apply_batch(db_session, batch.id)

    assert apply_res["status"] == "applied"
    derived_snapshot_id = apply_res["derived_snapshot_id"]

    derived_snapshot = db_session.get(ProjectSnapshot, derived_snapshot_id)
    assert derived_snapshot.parent_snapshot_id == ctx["snapshot"].id
    assert derived_snapshot.derivation_type == "fix_batch"

    # Original workspace byte-for-byte unchanged (Req 14)
    assert ctx["f1"].read_text(encoding="utf-8") == "import math\nimport os\n\nprint('hello')\n"
    assert ctx["f2"].read_text(encoding="utf-8") == "import sys\nimport re\n\ndef helper():\n    return 42\n"

    # Derived workspace contains transformations (Req 15)
    derived_f1 = Path(derived_snapshot.workspace_path) / "app.py"
    derived_f2 = Path(derived_snapshot.workspace_path) / "utils.py"

    assert "import math" not in derived_f1.read_text(encoding="utf-8")
    assert "import os" not in derived_f1.read_text(encoding="utf-8")
    assert "import sys" not in derived_f2.read_text(encoding="utf-8")
    assert "import re" in derived_f2.read_text(encoding="utf-8")


def test_16_stale_preview_rejected(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    auto_recs = [r for r in ctx["recs"] if r.fixability == "automatic"]
    batch = engine.preview_batch(db_session, ctx["evaluation"].id, [r.id for r in auto_recs])

    # Modify source file after preview
    ctx["f1"].write_text("import math\nimport os\n# modified\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        engine.apply_batch(db_session, batch.id)
    assert exc.value.status_code == 409
    assert "Source changed" in exc.value.detail


def test_18_batch_apply_idempotent(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    auto_recs = [r for r in ctx["recs"] if r.fixability == "automatic"]
    batch = engine.preview_batch(db_session, ctx["evaluation"].id, [r.id for r in auto_recs])

    engine.apply_batch(db_session, batch.id)

    with pytest.raises(HTTPException) as exc:
        engine.apply_batch(db_session, batch.id)
    assert exc.value.status_code == 409


def test_19_22_batch_verification(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()
    v_engine = VerificationEngine()

    auto_recs = [r for r in ctx["recs"] if r.fixability == "automatic"]
    batch = engine.preview_batch(db_session, ctx["evaluation"].id, [r.id for r in auto_recs])
    engine.apply_batch(db_session, batch.id)

    v_result1 = v_engine.verify_batch(db_session, batch.id)
    assert v_result1["status"] in {"verified", "regression"}
    assert v_result1["target_finding_status"] == "resolved"

    # Idempotency check (Req 22)
    v_result2 = v_engine.verify_batch(db_session, batch.id)
    assert v_result1["id"] == v_result2["id"]


def test_23_continue_from_derived_workflow(client, db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    auto_recs = [r for r in ctx["recs"] if r.fixability == "automatic"]
    batch = engine.preview_batch(db_session, ctx["evaluation"].id, [r.id for r in auto_recs])
    apply_res = engine.apply_batch(db_session, batch.id)
    derived_id = apply_res["derived_snapshot_id"]

    # Start new evaluation cycle from derived snapshot
    res = client.post(f"/api/snapshots/{derived_id}/evaluations")
    assert res.status_code == 201
    new_eval_data = res.json()
    assert new_eval_data["snapshot_id"] == derived_id


def test_24_25_existing_single_fix_workflow_preserved(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()
    v_engine = VerificationEngine()

    f401_rec = next(r for r in ctx["recs"] if r.rule_id == "F401")
    proposal = engine.preview(db_session, f401_rec, ctx["evaluation"])

    apply_result = apply_fix(proposal.id, db_session)
    assert apply_result["status"] == "applied"

    v_res = v_engine.verify(db_session, proposal.id)
    assert v_res["status"] in {"verified", "regression"}


def test_26_openapi_phase7_routes():
    from app.main import app as production_app

    paths = production_app.openapi()["paths"]

    assert "/api/evaluations/{evaluation_id}/fixes/preview-batch" in paths
    assert "post" in paths["/api/evaluations/{evaluation_id}/fixes/preview-batch"]

    assert "/api/fix-batches/{batch_id}/apply" in paths
    assert "post" in paths["/api/fix-batches/{batch_id}/apply"]

    assert "/api/fix-batches/{batch_id}/verify" in paths
    assert "post" in paths["/api/fix-batches/{batch_id}/verify"]

    assert "/api/fix-batches/{batch_id}/verification" in paths
    assert "get" in paths["/api/fix-batches/{batch_id}/verification"]

    assert "/api/snapshots/{snapshot_id}/evaluations" in paths
    assert "post" in paths["/api/snapshots/{snapshot_id}/evaluations"]


def test_migration_1_phase6_legacy_db(tmp_path):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from app.database import initialize_database
    from app.models import FixVerification

    db_file = tmp_path / "legacy_phase6.db"
    legacy_engine = create_engine(f"sqlite:///{db_file}")

    with legacy_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE fix_verifications (
                id VARCHAR(36) PRIMARY KEY,
                fix_id VARCHAR(36) NOT NULL,
                original_evaluation_id VARCHAR(36) NOT NULL,
                verification_evaluation_id VARCHAR(36) NOT NULL,
                original_snapshot_id VARCHAR(36) NOT NULL,
                derived_snapshot_id VARCHAR(36) NOT NULL,
                status VARCHAR(30) NOT NULL,
                target_finding_status VARCHAR(30) NOT NULL,
                resolved_count INTEGER DEFAULT 0,
                remaining_count INTEGER DEFAULT 0,
                new_count INTEGER DEFAULT 0,
                created_at DATETIME
            )
        """))
        conn.execute(text("""
            INSERT INTO fix_verifications (id, fix_id, original_evaluation_id, verification_evaluation_id, original_snapshot_id, derived_snapshot_id, status, target_finding_status, resolved_count, remaining_count, new_count)
            VALUES ('old-v-1', 'fix-123', 'eval-1', 'eval-2', 'snap-1', 'snap-2', 'verified', 'resolved', 1, 0, 0)
        """))

    initialize_database(legacy_engine)

    with legacy_engine.begin() as conn:
        pragma_info = conn.execute(text('PRAGMA table_info("fix_verifications")')).fetchall()
        fix_id_col = next(col for col in pragma_info if col[1] == "fix_id")
        batch_id_col = next((col for col in pragma_info if col[1] == "batch_id"), None)

        assert fix_id_col[3] == 0
        assert batch_id_col is not None
        assert batch_id_col[3] == 0

    SessionLocal = sessionmaker(bind=legacy_engine)
    session = SessionLocal()
    old_row = session.get(FixVerification, "old-v-1")
    assert old_row is not None
    assert old_row.fix_id == "fix-123"
    assert old_row.batch_id is None
    session.close()

    initialize_database(legacy_engine)
    with legacy_engine.begin() as conn:
        pragma_info_2 = conn.execute(text('PRAGMA table_info("fix_verifications")')).fetchall()
        fix_id_col_2 = next(col for col in pragma_info_2 if col[1] == "fix_id")
        assert fix_id_col_2[3] == 0


def test_migration_2_partially_migrated_phase7_db(tmp_path):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from app.database import initialize_database
    from app.models import FixVerification

    db_file = tmp_path / "partially_migrated.db"
    pm_engine = create_engine(f"sqlite:///{db_file}")

    with pm_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE fix_verifications (
                id VARCHAR(36) PRIMARY KEY,
                fix_id VARCHAR(36) NOT NULL,
                batch_id VARCHAR(36) NULL,
                original_evaluation_id VARCHAR(36) NOT NULL,
                verification_evaluation_id VARCHAR(36) NOT NULL,
                original_snapshot_id VARCHAR(36) NOT NULL,
                derived_snapshot_id VARCHAR(36) NOT NULL,
                status VARCHAR(30) NOT NULL,
                target_finding_status VARCHAR(30) NOT NULL,
                resolved_count INTEGER DEFAULT 0,
                remaining_count INTEGER DEFAULT 0,
                new_count INTEGER DEFAULT 0,
                created_at DATETIME
            )
        """))
        conn.execute(text("""
            INSERT INTO fix_verifications (id, fix_id, batch_id, original_evaluation_id, verification_evaluation_id, original_snapshot_id, derived_snapshot_id, status, target_finding_status, resolved_count, remaining_count, new_count)
            VALUES ('old-v-2', 'fix-456', NULL, 'eval-1', 'eval-2', 'snap-1', 'snap-2', 'verified', 'resolved', 1, 0, 0)
        """))

    initialize_database(pm_engine)

    with pm_engine.begin() as conn:
        pragma_info = conn.execute(text('PRAGMA table_info("fix_verifications")')).fetchall()
        fix_id_col = next(col for col in pragma_info if col[1] == "fix_id")
        assert fix_id_col[3] == 0

    SessionLocal = sessionmaker(bind=pm_engine)
    session = SessionLocal()
    row = session.get(FixVerification, "old-v-2")
    assert row is not None
    assert row.fix_id == "fix-456"
    session.close()


def test_migration_3_batch_verification_persistence(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()
    v_engine = VerificationEngine()

    auto_recs = [r for r in ctx["recs"] if r.fixability == "automatic"]
    batch = engine.preview_batch(db_session, ctx["evaluation"].id, [r.id for r in auto_recs])
    engine.apply_batch(db_session, batch.id)

    v_result = v_engine.verify_batch(db_session, batch.id)
    assert v_result["batch_id"] == batch.id
    assert v_result["fix_id"] is None

    row = db_session.query(FixVerification).filter_by(batch_id=batch.id).first()
    assert row is not None
    assert row.fix_id is None
    assert row.batch_id == batch.id


def test_migration_4_single_fix_backward_compatibility(db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()
    v_engine = VerificationEngine()

    f401_rec = next(r for r in ctx["recs"] if r.rule_id == "F401")
    proposal = engine.preview(db_session, f401_rec, ctx["evaluation"])
    apply_fix(proposal.id, db_session)

    v_res = v_engine.verify(db_session, proposal.id)
    assert v_res["fix_id"] == proposal.id
    assert v_res["batch_id"] is None

    row = db_session.query(FixVerification).filter_by(fix_id=proposal.id).first()
    assert row is not None
    assert row.fix_id == proposal.id
    assert row.batch_id is None


def test_migration_5_full_api_integration(client, db_session, tmp_path):
    ctx = setup_multi_fix_repo(db_session, tmp_path)
    engine = RecommendationEngine()

    auto_recs = [r for r in ctx["recs"] if r.fixability == "automatic"]
    batch = engine.preview_batch(db_session, ctx["evaluation"].id, [r.id for r in auto_recs])
    engine.apply_batch(db_session, batch.id)

    post_res = client.post(f"/api/fix-batches/{batch.id}/verify")
    assert post_res.status_code == 200
    res_json = post_res.json()
    assert res_json["batch_id"] == batch.id
    assert res_json["fix_id"] is None

    get_res = client.get(f"/api/fix-batches/{batch.id}/verification")
    assert get_res.status_code == 200
    get_json = get_res.json()
    assert get_json["id"] == res_json["id"]


