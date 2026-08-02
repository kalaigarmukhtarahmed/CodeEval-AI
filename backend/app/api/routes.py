from pathlib import Path
import shutil
import uuid
from pydantic import BaseModel

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AgentEvent, ArchitectureAnalysis, ArchitectureFinding, CategoryScore, Evaluation, EvaluationCheck, Finding, FixProposal, PerformanceAnalysis, PerformanceFinding, Project, ProjectProfile, ProjectSnapshot, Recommendation, TestFailure, TestRun
from ..schemas import AgentEventResponse, EvaluationResponse, HealthResponse, PlanResponse, ProfileResponse, ProjectResponse, ProjectUploadResponse
from ..services.evaluation_planner import EvaluationPlanner
from ..services.project_detector import ProjectDetector
from ..services.evaluation_engine import EvaluationEngine
from ..services.scoring_engine import SCORING_VERSION, ScoringEngine, overall
from ..services.recommendation_engine import RecommendationEngine, digest, safe_file
from ..services.upload_service import save_and_extract_upload
from ..services.verification_engine import VerificationEngine

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/projects", response_model=ProjectUploadResponse, status_code=status.HTTP_201_CREATED)
async def create_project(file: UploadFile = File(...), db: Session = Depends(get_db)) -> ProjectUploadResponse:
    safe_archive = await save_and_extract_upload(file)
    project = Project(name=Path(file.filename or "project.zip").stem, status="uploaded")
    snapshot = ProjectSnapshot(
        project=project,
        archive_path=str(safe_archive.archive_path),
        workspace_path=str(safe_archive.workspace_path),
        archive_size_bytes=safe_archive.archive_size_bytes,
        file_count=safe_archive.file_count,
        uncompressed_size_bytes=safe_archive.uncompressed_size_bytes,
    )
    try:
        db.add_all([project, snapshot])
        db.commit()
        db.refresh(project)
    except Exception:
        db.rollback()
        safe_archive.archive_path.unlink(missing_ok=True)
        shutil.rmtree(safe_archive.workspace_path, ignore_errors=True)
        raise
    return ProjectUploadResponse(project_id=project.id, name=project.name, status=project.status)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _get_evaluation(evaluation_id: str, db: Session) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    return evaluation


@router.post("/projects/{project_id}/evaluations", response_model=EvaluationResponse, status_code=status.HTTP_201_CREATED)
def create_evaluation(project_id: str, db: Session = Depends(get_db)) -> Evaluation:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    snapshot = (
        db.query(ProjectSnapshot)
        .filter(ProjectSnapshot.project_id == project_id)
        .order_by(ProjectSnapshot.created_at.desc())
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=409, detail="Project has no uploaded snapshot to inspect.")
    evaluation = Evaluation(project_id=project.id, snapshot_id=snapshot.id, status="analyzing")
    db.add(evaluation)
    db.flush()
    evaluation_id = evaluation.id
    db.add(AgentEvent(evaluation_id=evaluation_id, stage="ANALYZE", status="started", message="Repository inspection started", metadata_json=None))
    db.commit()
    try:
        detection = ProjectDetector().inspect(snapshot.workspace_path)
        profile = ProjectProfile(
            project_id=project.id, snapshot_id=snapshot.id, evaluation_id=evaluation_id,
            total_source_files=detection.total_source_files, total_source_lines=detection.total_source_lines,
            test_file_count=detection.test_file_count, languages_json=detection.languages,
            language_lines_json=detection.language_lines, language_evidence_json=detection.language_evidence,
            frameworks_json=detection.frameworks, package_managers_json=detection.package_managers,
            test_frameworks_json=detection.test_frameworks, test_directories_json=detection.test_directories,
            manifest_files_json=detection.manifest_files, source_directories_json=detection.source_directories,
            configuration_files_json=detection.configuration_files,
        )
        db.add(profile)
        db.add_all([
            AgentEvent(evaluation_id=evaluation_id, stage="ANALYZE", status="completed", message="Repository inspection completed", metadata_json={"source_file_count": detection.total_source_files, "source_line_count": detection.total_source_lines}),
            AgentEvent(evaluation_id=evaluation_id, stage="DETECT", status="completed", message="Technology stack detected", metadata_json={"languages": sorted(detection.languages), "frameworks": [item["name"] for item in detection.frameworks]}),
            AgentEvent(evaluation_id=evaluation_id, stage="PLAN", status="started", message="Evaluation planning started", metadata_json={"planner_version": EvaluationPlanner.version}),
        ])
        plan = EvaluationPlanner().create_plan(detection)
        evaluation.plan_json = plan
        evaluation.planner_version = EvaluationPlanner.version
        evaluation.status = "planned"
        db.add(AgentEvent(evaluation_id=evaluation_id, stage="PLAN", status="completed", message="Evaluation plan generated", metadata_json={"planned_check_count": len(plan), "planner_version": EvaluationPlanner.version}))
        db.commit()
        db.refresh(evaluation)
        return evaluation
    except Exception as error:
        db.rollback()
        failed = db.get(Evaluation, evaluation_id)
        if failed is not None:
            failed.status = "failed"
            db.add(AgentEvent(evaluation_id=failed.id, stage="ANALYZE", status="failed", message="Repository inspection failed", metadata_json={"error_type": type(error).__name__}))
            db.commit()
        raise HTTPException(status_code=500, detail="Repository analysis could not be completed safely.") from error


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationResponse)
def get_evaluation(evaluation_id: str, db: Session = Depends(get_db)) -> Evaluation:
    return _get_evaluation(evaluation_id, db)


@router.get("/evaluations/{evaluation_id}/profile", response_model=ProfileResponse)
def get_profile(evaluation_id: str, db: Session = Depends(get_db)) -> ProfileResponse:
    evaluation = _get_evaluation(evaluation_id, db)
    profile = evaluation.profile
    if profile is None:
        raise HTTPException(status_code=409, detail="Project profile is not available for this evaluation.")
    return ProfileResponse(
        evaluation_id=evaluation.id, total_source_files=profile.total_source_files, total_source_lines=profile.total_source_lines,
        test_file_count=profile.test_file_count, languages=profile.languages_json, language_lines=profile.language_lines_json,
        frameworks=profile.frameworks_json, package_managers=profile.package_managers_json, test_frameworks=profile.test_frameworks_json,
        test_directories=profile.test_directories_json, manifest_files=profile.manifest_files_json,
        source_directories=profile.source_directories_json, configuration_files=profile.configuration_files_json,
    )


@router.get("/evaluations/{evaluation_id}/plan", response_model=PlanResponse)
def get_plan(evaluation_id: str, db: Session = Depends(get_db)) -> PlanResponse:
    evaluation = _get_evaluation(evaluation_id, db)
    if evaluation.plan_json is None or evaluation.planner_version is None:
        raise HTTPException(status_code=409, detail="Evaluation plan is not available for this evaluation.")
    return PlanResponse(evaluation_id=evaluation.id, planner_version=evaluation.planner_version, checks=evaluation.plan_json)


@router.get("/evaluations/{evaluation_id}/timeline", response_model=list[AgentEventResponse])
def get_timeline(evaluation_id: str, db: Session = Depends(get_db)) -> list[AgentEvent]:
    _get_evaluation(evaluation_id, db)
    return db.query(AgentEvent).filter(AgentEvent.evaluation_id == evaluation_id).order_by(AgentEvent.created_at, AgentEvent.id).all()

@router.post("/evaluations/{evaluation_id}/run", response_model=EvaluationResponse)
def run_evaluation(evaluation_id: str, db: Session = Depends(get_db)):
    evaluation = _get_evaluation(evaluation_id, db)
    if evaluation.plan_json is None: raise HTTPException(status_code=409, detail="Evaluation plan is not available.")
    return EvaluationEngine().run(db, evaluation)

@router.get("/evaluations/{evaluation_id}/checks")
def get_checks(evaluation_id: str, db: Session = Depends(get_db)):
    _get_evaluation(evaluation_id, db)
    return db.query(EvaluationCheck).filter(EvaluationCheck.evaluation_id == evaluation_id).all()

@router.get("/evaluations/{evaluation_id}/findings")
def get_findings(evaluation_id: str, category: str | None = None, severity: str | None = None, tool: str | None = None, file: str | None = None, db: Session = Depends(get_db)):
    _get_evaluation(evaluation_id, db); query=db.query(Finding).filter(Finding.evaluation_id == evaluation_id)
    for column, value in ((Finding.category,category),(Finding.severity,severity),(Finding.tool,tool),(Finding.file_path,file)):
        if value: query=query.filter(column==value)
    return query.order_by(Finding.severity, Finding.file_path, Finding.line_start).all()

@router.get("/evaluations/{evaluation_id}/findings/{finding_id}")
def get_finding(evaluation_id: str, finding_id: str, db: Session = Depends(get_db)):
    finding=db.query(Finding).filter(Finding.evaluation_id==evaluation_id, Finding.id==finding_id).first()
    if finding is None: raise HTTPException(status_code=404, detail="Finding not found.")
    return finding

@router.post("/evaluations/{evaluation_id}/score")
def score_evaluation(evaluation_id: str, db: Session = Depends(get_db)):
    evaluation = _get_evaluation(evaluation_id, db)
    if evaluation.status not in {"completed", "completed_with_errors"}: raise HTTPException(status_code=409, detail="Static evaluation must complete before scoring.")
    scores=ScoringEngine().score(db,evaluation)
    db.add(AgentEvent(evaluation_id=evaluation.id,stage="REVIEW",status="completed",message="Deterministic scores generated",metadata_json={"scoring_version":SCORING_VERSION})); db.commit()
    return {"evaluation_id":evaluation.id,"scoring_version":SCORING_VERSION,"overall":overall(scores),"categories":[{"category":s.category,"status":s.status,"score":s.score,"explanation":s.explanation,"evidence_summary":s.evidence_summary} for s in scores]}

@router.get("/evaluations/{evaluation_id}/scores")
def get_scores(evaluation_id: str, db: Session = Depends(get_db)):
    _get_evaluation(evaluation_id,db); scores=db.query(CategoryScore).filter(CategoryScore.evaluation_id==evaluation_id).order_by(CategoryScore.category).all()
    return {"evaluation_id":evaluation_id,"scoring_version":SCORING_VERSION,"overall":overall(scores),"categories":[{"category":s.category,"status":s.status,"score":s.score,"explanation":s.explanation,"evidence_summary":s.evidence_summary} for s in scores]}

@router.get("/evaluations/{evaluation_id}/tests")
def get_tests(evaluation_id: str, db: Session = Depends(get_db)):
    _get_evaluation(evaluation_id, db)
    test_run = db.query(TestRun).filter(TestRun.evaluation_id == evaluation_id).order_by(TestRun.created_at.desc()).first()
    if test_run is None:
        return {"status": "not_discovered", "framework": "pytest", "tests_collected": 0, "tests_passed": 0, "tests_failed": 0, "tests_skipped": 0, "tests_errors": 0, "duration_ms": None, "coverage_percent": None, "execution_mode": "disabled", "failures": []}
    return {
        "id": test_run.id,
        "status": test_run.status,
        "framework": test_run.framework,
        "tests_collected": test_run.tests_collected,
        "tests_passed": test_run.tests_passed,
        "tests_failed": test_run.tests_failed,
        "tests_errors": test_run.tests_errors,
        "tests_skipped": test_run.tests_skipped,
        "duration_ms": test_run.duration_ms,
        "coverage_percent": test_run.coverage_percent,
        "execution_mode": test_run.execution_mode,
        "blocked_reason": test_run.blocked_reason,
        "stdout_summary": test_run.stdout_summary,
        "stderr_summary": test_run.stderr_summary,
        "failures": [
            {
                "id": f.id,
                "node_id": f.node_id,
                "file_path": f.file_path,
                "test_name": f.test_name,
                "failure_type": f.failure_type,
                "message": f.message
            } for f in test_run.failures
        ]
    }

@router.get("/evaluations/{evaluation_id}/report")
def get_report(evaluation_id: str, db: Session = Depends(get_db)):
    evaluation = _get_evaluation(evaluation_id, db)
    profile = evaluation.profile
    scores = db.query(CategoryScore).filter(CategoryScore.evaluation_id == evaluation_id).order_by(CategoryScore.category).all()
    findings = db.query(Finding).filter(Finding.evaluation_id == evaluation_id).all()
    test_run = db.query(TestRun).filter(TestRun.evaluation_id == evaluation_id).order_by(TestRun.created_at.desc()).first()
    from collections import Counter
    test_run_data = None
    if test_run:
        test_run_data = {
            "id": test_run.id,
            "status": test_run.status,
            "framework": test_run.framework,
            "tests_collected": test_run.tests_collected,
            "tests_passed": test_run.tests_passed,
            "tests_failed": test_run.tests_failed,
            "tests_errors": test_run.tests_errors,
            "tests_skipped": test_run.tests_skipped,
            "duration_ms": test_run.duration_ms,
            "coverage_percent": test_run.coverage_percent,
            "execution_mode": test_run.execution_mode,
            "blocked_reason": test_run.blocked_reason,
            "stdout_summary": test_run.stdout_summary,
            "stderr_summary": test_run.stderr_summary,
            "failures": [
                {
                    "id": f.id,
                    "node_id": f.node_id,
                    "file_path": f.file_path,
                    "test_name": f.test_name,
                    "failure_type": f.failure_type,
                    "message": f.message
                } for f in test_run.failures
            ]
        }
    arch_analysis = db.query(ArchitectureAnalysis).filter(ArchitectureAnalysis.evaluation_id == evaluation_id).order_by(ArchitectureAnalysis.created_at.desc()).first()
    arch_data = None
    if arch_analysis:
        arch_data = {
            "id": arch_analysis.id,
            "status": arch_analysis.status,
            "score": arch_analysis.score,
            "metrics": {
                "source_file_count": arch_analysis.source_file_count,
                "package_count": arch_analysis.package_count,
                "module_count": arch_analysis.module_count,
                "dependency_edge_count": arch_analysis.dependency_edge_count,
                "circular_dependency_count": arch_analysis.circular_dependency_count,
                "high_fan_out_count": arch_analysis.high_fan_out_count,
                "largest_file_lines": arch_analysis.largest_file_lines,
                "average_file_lines": arch_analysis.average_file_lines,
                "architecture_docs_present": arch_analysis.architecture_docs_present
            },
            "explanation": arch_analysis.explanation,
            "findings": [
                {
                    "id": f.id,
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "category": f.category,
                    "file_path": f.file_path,
                    "message": f.message,
                    "evidence": f.evidence
                } for f in arch_analysis.findings
            ]
        }

    perf_analysis = db.query(PerformanceAnalysis).filter(PerformanceAnalysis.evaluation_id == evaluation_id).order_by(PerformanceAnalysis.created_at.desc()).first()
    perf_data = None
    if perf_analysis:
        perf_data = {
            "id": perf_analysis.id,
            "score": perf_analysis.score,
            "metrics": {
                "functions": perf_analysis.functions,
                "loops": perf_analysis.loops,
                "nested_loops": perf_analysis.nested_loops,
                "average_complexity": perf_analysis.average_complexity
            },
            "benchmark_information": {
                "benchmark_enabled": perf_analysis.benchmark_enabled,
                "benchmark_time_ms": perf_analysis.benchmark_time_ms
            },
            "execution_mode": "benchmark" if perf_analysis.benchmark_enabled else "static_only",
            "findings": [
                {
                    "id": f.id,
                    "rule": f.rule,
                    "severity": f.severity,
                    "file_path": f.file_path,
                    "line": f.line,
                    "message": f.message,
                    "penalty": f.penalty
                } for f in perf_analysis.findings
            ]
        }

    return {
        "evaluation_id": evaluation_id,
        "evaluation_status": evaluation.status,
        "scoring_version": SCORING_VERSION,
        "overall": overall(scores),
        "categories": [{"category": s.category, "status": s.status, "score": s.score, "explanation": s.explanation, "evidence_summary": s.evidence_summary} for s in scores],
        "profile": {"languages": profile.languages_json, "total_source_files": profile.total_source_files, "total_source_lines": profile.total_source_lines} if profile else None,
        "checks": [{"tool": c.tool, "status": c.status, "finding_count": c.finding_count, "duration_ms": c.duration_ms} for c in evaluation.checks],
        "test_run": test_run_data,
        "architecture_analysis": arch_data,
        "performance_analysis": perf_data,
        "finding_counts": {"severity": dict(Counter(f.severity for f in findings)), "tool": dict(Counter(f.tool for f in findings))},
        "top_findings": [{"id": f.id, "severity": f.severity, "category": f.category, "tool": f.tool, "rule_id": f.rule_id, "file_path": f.file_path, "line_start": f.line_start, "message": f.message, "evidence": f.evidence} for f in findings[:20]],
        "timeline_summary": [e.message for e in evaluation.agent_events]
    }


@router.get("/evaluations/{evaluation_id}/architecture")
def get_architecture(evaluation_id: str, db: Session = Depends(get_db)):
    _get_evaluation(evaluation_id, db)
    arch_analysis = db.query(ArchitectureAnalysis).filter(ArchitectureAnalysis.evaluation_id == evaluation_id).order_by(ArchitectureAnalysis.created_at.desc()).first()
    if not arch_analysis:
        return {"status": "not_run", "score": None, "metrics": None, "explanation": "Architecture analysis not performed for this evaluation.", "findings": []}
    return {
        "id": arch_analysis.id,
        "evaluation_id": arch_analysis.evaluation_id,
        "snapshot_id": arch_analysis.snapshot_id,
        "status": arch_analysis.status,
        "score": arch_analysis.score,
        "metrics": {
            "source_file_count": arch_analysis.source_file_count,
            "package_count": arch_analysis.package_count,
            "module_count": arch_analysis.module_count,
            "dependency_edge_count": arch_analysis.dependency_edge_count,
            "circular_dependency_count": arch_analysis.circular_dependency_count,
            "high_fan_out_count": arch_analysis.high_fan_out_count,
            "largest_file_lines": arch_analysis.largest_file_lines,
            "average_file_lines": arch_analysis.average_file_lines,
            "architecture_docs_present": arch_analysis.architecture_docs_present
        },
        "explanation": arch_analysis.explanation,
        "findings": [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "category": f.category,
                "file_path": f.file_path,
                "message": f.message,
                "evidence": f.evidence
            } for f in arch_analysis.findings
        ]
    }


@router.get("/evaluations/{evaluation_id}/performance")
def get_performance(evaluation_id: str, db: Session = Depends(get_db)):
    _get_evaluation(evaluation_id, db)
    perf_analysis = db.query(PerformanceAnalysis).filter(PerformanceAnalysis.evaluation_id == evaluation_id).order_by(PerformanceAnalysis.created_at.desc()).first()
    if not perf_analysis:
        return {
            "status": "not_run",
            "score": None,
            "metrics": None,
            "findings": [],
            "benchmark_information": {
                "benchmark_enabled": False,
                "benchmark_time_ms": None
            },
            "execution_mode": "static_only"
        }
    return {
        "id": perf_analysis.id,
        "evaluation_id": perf_analysis.evaluation_id,
        "snapshot_id": perf_analysis.snapshot_id,
        "status": "completed",
        "score": perf_analysis.score,
        "metrics": {
            "functions": perf_analysis.functions,
            "loops": perf_analysis.loops,
            "nested_loops": perf_analysis.nested_loops,
            "average_complexity": perf_analysis.average_complexity,
        },
        "findings": [
            {
                "id": f.id,
                "rule": f.rule,
                "severity": f.severity,
                "file_path": f.file_path,
                "line": f.line,
                "message": f.message,
                "penalty": f.penalty,
            } for f in perf_analysis.findings
        ],
        "benchmark_information": {
            "benchmark_enabled": perf_analysis.benchmark_enabled,
            "benchmark_time_ms": perf_analysis.benchmark_time_ms
        },
        "execution_mode": "benchmark" if perf_analysis.benchmark_enabled else "static_only"
    }

@router.post("/evaluations/{evaluation_id}/recommendations")
def generate_recommendations(evaluation_id:str,db:Session=Depends(get_db)):
    return RecommendationEngine().generate(db,_get_evaluation(evaluation_id,db))
@router.get("/evaluations/{evaluation_id}/recommendations")
def get_recommendations(evaluation_id:str,db:Session=Depends(get_db)):
    _get_evaluation(evaluation_id,db); return db.query(Recommendation).filter(Recommendation.evaluation_id==evaluation_id).all()
@router.post("/recommendations/{recommendation_id}/preview")
def preview_fix(recommendation_id:str,db:Session=Depends(get_db)):
    recommendation=db.get(Recommendation,recommendation_id)
    if not recommendation: raise HTTPException(404,"Recommendation not found.")
    try:return RecommendationEngine().preview(db,recommendation,_get_evaluation(recommendation.evaluation_id,db))
    except ValueError as error: raise HTTPException(409,str(error))
@router.post("/fixes/{fix_id}/apply")
def apply_fix(fix_id:str,db:Session=Depends(get_db)):
    fix=db.get(FixProposal,fix_id)
    if not fix or fix.status!="proposed": raise HTTPException(409,"Fix proposal is unavailable.")
    evaluation=_get_evaluation(fix.evaluation_id,db)
    try:
        source=safe_file(evaluation.snapshot.workspace_path,fix.file_path)
    except ValueError as error:
        raise HTTPException(409,str(error))
    if digest(source.read_text(encoding="utf-8-sig"))!=fix.original_content_hash: raise HTTPException(409,"Source changed since fix preview was generated.")
    derived=Path(evaluation.snapshot.workspace_path).parent / f"derived-{uuid.uuid4()}"; shutil.copytree(evaluation.snapshot.workspace_path,derived,symlinks=True); target=safe_file(derived,fix.file_path); target.write_text(fix.proposed_content,encoding="utf-8")
    snapshot=ProjectSnapshot(project_id=evaluation.project_id,archive_path=evaluation.snapshot.archive_path,workspace_path=str(derived),archive_size_bytes=0,file_count=0,uncompressed_size_bytes=0,parent_snapshot_id=evaluation.snapshot_id,derivation_type="fix")
    db.add(snapshot); fix.status="applied"; db.commit(); return {"fix_id":fix.id,"status":"applied","derived_snapshot_id":snapshot.id,"message":"Change applied to derived snapshot. Verification pending."}

@router.post("/fixes/{fix_id}/verify")
def verify_fix(fix_id: str, db: Session = Depends(get_db)):
    return VerificationEngine().verify(db, fix_id)

@router.get("/fixes/{fix_id}/verification")
def get_fix_verification(fix_id: str, db: Session = Depends(get_db)):
    return VerificationEngine().get_verification(db, fix_id)

from pydantic import BaseModel

class PreviewBatchRequest(BaseModel):
    recommendation_ids: list[str]

@router.post("/evaluations/{evaluation_id}/fixes/preview-batch")
def preview_batch(evaluation_id: str, payload: PreviewBatchRequest, db: Session = Depends(get_db)):
    return RecommendationEngine().preview_batch(db, evaluation_id, payload.recommendation_ids)

@router.post("/fix-batches/{batch_id}/apply")
def apply_batch(batch_id: str, db: Session = Depends(get_db)):
    return RecommendationEngine().apply_batch(db, batch_id)

@router.post("/fix-batches/{batch_id}/verify")
def verify_batch(batch_id: str, db: Session = Depends(get_db)):
    return VerificationEngine().verify_batch(db, batch_id)

@router.get("/fix-batches/{batch_id}/verification")
def get_batch_verification(batch_id: str, db: Session = Depends(get_db)):
    return VerificationEngine().get_batch_verification(db, batch_id)

@router.post("/snapshots/{snapshot_id}/evaluations", response_model=EvaluationResponse, status_code=status.HTTP_201_CREATED)
def create_evaluation_from_snapshot(snapshot_id: str, db: Session = Depends(get_db)) -> Evaluation:
    snapshot = db.get(ProjectSnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    evaluation = Evaluation(project_id=snapshot.project_id, snapshot_id=snapshot.id, status="analyzing")
    db.add(evaluation)
    db.flush()
    evaluation_id = evaluation.id
    db.add(AgentEvent(evaluation_id=evaluation_id, stage="ANALYZE", status="started", message="Derived repository inspection started", metadata_json={"snapshot_id": snapshot.id}))
    db.commit()
    try:
        detection = ProjectDetector().inspect(snapshot.workspace_path)
        profile = ProjectProfile(
            project_id=snapshot.project_id, snapshot_id=snapshot.id, evaluation_id=evaluation_id,
            total_source_files=detection.total_source_files, total_source_lines=detection.total_source_lines,
            test_file_count=detection.test_file_count, languages_json=detection.languages,
            language_lines_json=detection.language_lines, language_evidence_json=detection.language_evidence,
            frameworks_json=detection.frameworks, package_managers_json=detection.package_managers,
            test_frameworks_json=detection.test_frameworks, test_directories_json=detection.test_directories,
            manifest_files_json=detection.manifest_files, source_directories_json=detection.source_directories,
            configuration_files_json=detection.configuration_files,
        )
        db.add(profile)
        plan = EvaluationPlanner().create_plan(detection)
        evaluation.plan_json = plan
        evaluation.planner_version = EvaluationPlanner.version
        evaluation.status = "planned"
        db.add(AgentEvent(evaluation_id=evaluation_id, stage="PLAN", status="completed", message="Evaluation plan generated for derived snapshot", metadata_json={"planned_check_count": len(plan)}))
        db.commit()
        db.refresh(evaluation)
        return evaluation
    except Exception as error:
        db.rollback()
        failed = db.get(Evaluation, evaluation_id)
        if failed is not None:
            failed.status = "failed"
            db.commit()
        raise HTTPException(status_code=500, detail="Derived repository analysis failed.") from error
