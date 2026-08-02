from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ..models import AgentEvent, CategoryScore, Evaluation, Finding, FixBatch, FixProposal, FixVerification, ProjectProfile, ProjectSnapshot, Recommendation
from .project_detector import ProjectDetector
from .evaluation_planner import EvaluationPlanner
from .evaluation_engine import EvaluationEngine
from .scoring_engine import ScoringEngine, overall
from .recommendation_engine import safe_file, digest


def finding_key(finding: Finding) -> tuple[str, str, str, str, str]:
    """Normalized identity key for before/after finding comparison across snapshots."""
    return (
        finding.category or "",
        finding.tool or "",
        finding.rule_id or "",
        finding.file_path or "",
        finding.message or ""
    )


def format_verification_response(db: Session, verification: FixVerification) -> dict:
    fix = db.get(FixProposal, verification.fix_id) if verification.fix_id else None
    batch = db.get(FixBatch, verification.batch_id) if verification.batch_id else None

    before_findings = db.query(Finding).filter(Finding.evaluation_id == verification.original_evaluation_id).all()
    after_findings = db.query(Finding).filter(Finding.evaluation_id == verification.verification_evaluation_id).all()

    before_scores = db.query(CategoryScore).filter(CategoryScore.evaluation_id == verification.original_evaluation_id).all()
    after_scores = db.query(CategoryScore).filter(CategoryScore.evaluation_id == verification.verification_evaluation_id).all()

    before_keys = {finding_key(f): f for f in before_findings}
    after_keys = {finding_key(f): f for f in after_findings}

    resolved = [f for key, f in before_keys.items() if key not in after_keys]
    remaining = [f for key, f in before_keys.items() if key in after_keys]
    new_findings = [f for key, f in after_keys.items() if key not in before_keys]

    target_details = []
    if fix and fix.recommendation:
        tf = next((f for f in before_findings if f.id == fix.recommendation.finding_id), None)
        target_rule_id = fix.recommendation.rule_id if fix.recommendation else (tf.rule_id if tf else None)
        target_file_path = fix.file_path if fix else (tf.file_path if tf else None)
        target_details.append({
            "rule_id": target_rule_id,
            "file_path": target_file_path,
            "before": "present",
            "after": "absent" if verification.target_finding_status == "resolved" else "present",
            "status": verification.target_finding_status
        })

    elif batch:
        for item in batch.items:
            rec = item.recommendation
            tf = next((f for f in before_findings if rec and f.id == rec.finding_id), None)
            rule_id = rec.rule_id if rec else (tf.rule_id if tf else None)
            file_path = item.file_path if item else (tf.file_path if tf else None)
            tf_absent = (finding_key(tf) not in after_keys) if tf else True
            target_details.append({
                "recommendation_id": item.recommendation_id,
                "rule_id": rule_id,
                "file_path": file_path,
                "before": "present",
                "after": "absent" if tf_absent else "present",
                "status": "resolved" if tf_absent else "not_resolved"
            })

    target_finding_summary = target_details[0] if len(target_details) == 1 else {
        "targets": target_details,
        "status": verification.target_finding_status
    }

    return {
        "id": verification.id,
        "fix_id": verification.fix_id,
        "batch_id": verification.batch_id,
        "status": verification.status,
        "target_finding_status": verification.target_finding_status,
        "original_evaluation_id": verification.original_evaluation_id,
        "verification_evaluation_id": verification.verification_evaluation_id,
        "original_snapshot_id": verification.original_snapshot_id,
        "derived_snapshot_id": verification.derived_snapshot_id,
        "target_finding": target_finding_summary,
        "target_details": target_details,
        "findings": {
            "before": len(before_findings),
            "after": len(after_findings),
            "resolved": len(resolved),
            "remaining": len(remaining),
            "new": len(new_findings),
            "details": {
                "resolved": [{"id": f.id, "severity": f.severity, "category": f.category, "tool": f.tool, "rule_id": f.rule_id, "file_path": f.file_path, "line_start": f.line_start, "message": f.message} for f in resolved],
                "remaining": [{"id": f.id, "severity": f.severity, "category": f.category, "tool": f.tool, "rule_id": f.rule_id, "file_path": f.file_path, "line_start": f.line_start, "message": f.message} for f in remaining],
                "new": [{"id": f.id, "severity": f.severity, "category": f.category, "tool": f.tool, "rule_id": f.rule_id, "file_path": f.file_path, "line_start": f.line_start, "message": f.message} for f in new_findings]
            }
        },
        "scores": {
            "before": {
                "overall": overall(before_scores)["score"],
                "categories": {s.category: {"score": s.score, "status": s.status} for s in before_scores}
            },
            "after": {
                "overall": overall(after_scores)["score"],
                "categories": {s.category: {"score": s.score, "status": s.status} for s in after_scores}
            }
        }
    }


class VerificationEngine:
    def verify(self, db: Session, fix_id: str) -> dict:
        fix = db.get(FixProposal, fix_id)
        if not fix:
            raise HTTPException(status_code=404, detail="Fix proposal not found.")
        if fix.status != "applied":
            raise HTTPException(status_code=409, detail="Fix proposal is unavailable or has not been applied.")

        original_eval = db.get(Evaluation, fix.evaluation_id)
        if not original_eval:
            raise HTTPException(status_code=404, detail="Original evaluation not found.")

        derived_snapshot = db.query(ProjectSnapshot).filter(
            ProjectSnapshot.parent_snapshot_id == fix.source_snapshot_id,
            ProjectSnapshot.derivation_type == "fix"
        ).order_by(ProjectSnapshot.created_at.desc()).first()

        if not derived_snapshot:
            raise HTTPException(status_code=409, detail="Derived snapshot does not exist for this applied fix.")

        try:
            workspace = Path(derived_snapshot.workspace_path).resolve()
            if not workspace.exists():
                raise ValueError("Derived workspace directory does not exist.")
        except Exception as err:
            raise HTTPException(status_code=409, detail=f"Derived workspace error: {err}")

        # Idempotency check
        existing_verification = db.query(FixVerification).filter_by(fix_id=fix.id).first()
        if existing_verification:
            verification_eval = db.get(Evaluation, existing_verification.verification_evaluation_id)
            if verification_eval and verification_eval.status in {"completed", "completed_with_errors"}:
                target_file = safe_file(derived_snapshot.workspace_path, fix.file_path)
                if digest(target_file.read_text(encoding="utf-8-sig")) == fix.proposed_content_hash:
                    return format_verification_response(db, existing_verification)

        new_eval = Evaluation(
            project_id=original_eval.project_id,
            snapshot_id=derived_snapshot.id,
            status="analyzing"
        )
        db.add(new_eval)
        db.flush()

        db.add_all([
            AgentEvent(evaluation_id=new_eval.id, stage="VERIFY", status="started", message="Fix verification started", metadata_json={"fix_id": fix.id}),
            AgentEvent(evaluation_id=new_eval.id, stage="ANALYZE", status="started", message="Derived snapshot evaluation started", metadata_json={"snapshot_id": derived_snapshot.id})
        ])
        db.commit()

        detection = ProjectDetector().inspect(derived_snapshot.workspace_path)
        profile = ProjectProfile(
            project_id=original_eval.project_id,
            snapshot_id=derived_snapshot.id,
            evaluation_id=new_eval.id,
            total_source_files=detection.total_source_files,
            total_source_lines=detection.total_source_lines,
            test_file_count=detection.test_file_count,
            languages_json=detection.languages,
            language_lines_json=detection.language_lines,
            language_evidence_json=detection.language_evidence,
            frameworks_json=detection.frameworks,
            package_managers_json=detection.package_managers,
            test_frameworks_json=detection.test_frameworks,
            test_directories_json=detection.test_directories,
            manifest_files_json=detection.manifest_files,
            source_directories_json=detection.source_directories,
            configuration_files_json=detection.configuration_files,
        )
        db.add(profile)
        plan = EvaluationPlanner().create_plan(detection)
        new_eval.plan_json = plan
        new_eval.planner_version = EvaluationPlanner.version
        new_eval.status = "planned"
        db.commit()

        EvaluationEngine().run(db, new_eval)
        ScoringEngine().score(db, new_eval)

        before_findings = db.query(Finding).filter(Finding.evaluation_id == original_eval.id).all()
        after_findings = db.query(Finding).filter(Finding.evaluation_id == new_eval.id).all()

        before_keys = {finding_key(f): f for f in before_findings}
        after_keys = {finding_key(f): f for f in after_findings}

        resolved_findings = [f for key, f in before_keys.items() if key not in after_keys]
        remaining_findings = [f for key, f in before_keys.items() if key in after_keys]
        new_findings = [f for key, f in after_keys.items() if key not in before_keys]

        target_original_finding = next((f for f in before_findings if fix and fix.recommendation and f.id == fix.recommendation.finding_id), None)
        target_resolved = False
        if target_original_finding:
            target_key = finding_key(target_original_finding)
            target_resolved = target_key not in after_keys
        else:
            target_resolved = len(resolved_findings) > 0

        target_finding_status = "resolved" if target_resolved else "not_resolved"
        verification_status = ("verified" if len(new_findings) == 0 else "regression") if target_resolved else "not_resolved"

        verification = FixVerification(
            fix_id=fix.id,
            original_evaluation_id=original_eval.id,
            verification_evaluation_id=new_eval.id,
            original_snapshot_id=original_eval.snapshot_id,
            derived_snapshot_id=derived_snapshot.id,
            status=verification_status,
            target_finding_status=target_finding_status,
            resolved_count=len(resolved_findings),
            remaining_count=len(remaining_findings),
            new_count=len(new_findings)
        )
        db.add(verification)

        message = "Fix verified" if verification_status == "verified" else (
            "Fix target resolved, but regression detected" if verification_status == "regression" else "Fix verification completed — target not resolved"
        )
        db.add(AgentEvent(evaluation_id=new_eval.id, stage="VERIFY", status="completed", message=message, metadata_json={"status": verification_status}))
        db.commit()

        return format_verification_response(db, verification)

    def verify_batch(self, db: Session, batch_id: str) -> dict:
        batch = db.get(FixBatch, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Fix batch not found.")
        if batch.status != "applied":
            raise HTTPException(status_code=409, detail="Fix batch is unavailable or has not been applied.")

        original_eval = db.get(Evaluation, batch.evaluation_id)
        if not original_eval:
            raise HTTPException(status_code=404, detail="Original evaluation not found.")

        derived_snapshot = db.get(ProjectSnapshot, batch.derived_snapshot_id) if batch.derived_snapshot_id else None
        if not derived_snapshot:
            raise HTTPException(status_code=409, detail="Derived snapshot does not exist for this applied batch.")

        # Idempotency check
        existing_verification = db.query(FixVerification).filter_by(batch_id=batch.id).first()
        if existing_verification:
            verification_eval = db.get(Evaluation, existing_verification.verification_evaluation_id)
            if verification_eval and verification_eval.status in {"completed", "completed_with_errors"}:
                return format_verification_response(db, existing_verification)

        new_eval = Evaluation(
            project_id=original_eval.project_id,
            snapshot_id=derived_snapshot.id,
            status="analyzing"
        )
        db.add(new_eval)
        db.flush()

        db.add_all([
            AgentEvent(evaluation_id=new_eval.id, stage="VERIFY", status="started", message="Batch fix verification started", metadata_json={"batch_id": batch.id}),
            AgentEvent(evaluation_id=new_eval.id, stage="ANALYZE", status="started", message="Derived snapshot evaluation started", metadata_json={"snapshot_id": derived_snapshot.id})
        ])
        db.commit()

        detection = ProjectDetector().inspect(derived_snapshot.workspace_path)
        profile = ProjectProfile(
            project_id=original_eval.project_id,
            snapshot_id=derived_snapshot.id,
            evaluation_id=new_eval.id,
            total_source_files=detection.total_source_files,
            total_source_lines=detection.total_source_lines,
            test_file_count=detection.test_file_count,
            languages_json=detection.languages,
            language_lines_json=detection.language_lines,
            language_evidence_json=detection.language_evidence,
            frameworks_json=detection.frameworks,
            package_managers_json=detection.package_managers,
            test_frameworks_json=detection.test_frameworks,
            test_directories_json=detection.test_directories,
            manifest_files_json=detection.manifest_files,
            source_directories_json=detection.source_directories,
            configuration_files_json=detection.configuration_files,
        )
        db.add(profile)
        plan = EvaluationPlanner().create_plan(detection)
        new_eval.plan_json = plan
        new_eval.planner_version = EvaluationPlanner.version
        new_eval.status = "planned"
        db.commit()

        EvaluationEngine().run(db, new_eval)
        ScoringEngine().score(db, new_eval)

        before_findings = db.query(Finding).filter(Finding.evaluation_id == original_eval.id).all()
        after_findings = db.query(Finding).filter(Finding.evaluation_id == new_eval.id).all()

        before_keys = {finding_key(f): f for f in before_findings}
        after_keys = {finding_key(f): f for f in after_findings}

        resolved_findings = [f for key, f in before_keys.items() if key not in after_keys]
        remaining_findings = [f for key, f in before_keys.items() if key in after_keys]
        new_findings = [f for key, f in after_keys.items() if key not in before_keys]

        # Targeted findings verification for batch
        target_findings_absent = []
        for item in batch.items:
            rec = item.recommendation
            tf = next((f for f in before_findings if rec and f.id == rec.finding_id), None)
            if tf:
                absent = finding_key(tf) not in after_keys
                target_findings_absent.append(absent)

        if all(target_findings_absent):
            target_finding_status = "resolved"
            verification_status = "verified" if len(new_findings) == 0 else "regression"
        elif any(target_findings_absent):
            target_finding_status = "partially_resolved"
            verification_status = "partially_resolved"
        else:
            target_finding_status = "not_resolved"
            verification_status = "not_resolved"

        verification = FixVerification(
            batch_id=batch.id,
            original_evaluation_id=original_eval.id,
            verification_evaluation_id=new_eval.id,
            original_snapshot_id=original_eval.snapshot_id,
            derived_snapshot_id=derived_snapshot.id,
            status=verification_status,
            target_finding_status=target_finding_status,
            resolved_count=len(resolved_findings),
            remaining_count=len(remaining_findings),
            new_count=len(new_findings)
        )
        db.add(verification)

        message = "Batch fixes verified" if verification_status == "verified" else f"Batch verification completed ({verification_status})"
        db.add(AgentEvent(evaluation_id=new_eval.id, stage="VERIFY", status="completed", message=message, metadata_json={"status": verification_status}))
        db.commit()

        return format_verification_response(db, verification)

    def get_verification(self, db: Session, fix_id: str) -> dict:
        verification = db.query(FixVerification).filter_by(fix_id=fix_id).first()
        if not verification:
            raise HTTPException(status_code=404, detail="Verification results not found for this fix proposal.")
        return format_verification_response(db, verification)

    def get_batch_verification(self, db: Session, batch_id: str) -> dict:
        verification = db.query(FixVerification).filter_by(batch_id=batch_id).first()
        if not verification:
            raise HTTPException(status_code=404, detail="Verification results not found for this fix batch.")
        return format_verification_response(db, verification)
