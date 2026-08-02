from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from ..models import AgentEvent, ArchitectureAnalysis, Evaluation, EvaluationCheck, Finding, PerformanceAnalysis, TestRun
from .architecture_analyzer import ArchitectureAnalyzer
from .performance_analyzer import PerformanceAnalyzer
from .static_analyzers import ADAPTERS
from .test_runner import TestRunner


class EvaluationEngine:
    def run(self, db: Session, evaluation: Evaluation):
        workspace = Path(evaluation.snapshot.workspace_path)
        db.query(Finding).filter(Finding.evaluation_id == evaluation.id).delete()
        db.query(EvaluationCheck).filter(EvaluationCheck.evaluation_id == evaluation.id).delete()
        db.query(TestRun).filter(TestRun.evaluation_id == evaluation.id).delete()
        db.query(ArchitectureAnalysis).filter(ArchitectureAnalysis.evaluation_id == evaluation.id).delete()
        db.query(PerformanceAnalysis).filter(PerformanceAnalysis.evaluation_id == evaluation.id).delete()

        evaluation.status = "running"
        db.add(AgentEvent(evaluation_id=evaluation.id, stage="EXECUTE", status="started", message="Evaluation started", metadata_json=None))
        db.commit()

        errors = False
        for plan in evaluation.plan_json or []:
            exec_mode = plan.get("execution_mode")
            if plan["tool"] == "architecture-analyzer" or plan.get("id") == "python-architecture":
                check = EvaluationCheck(
                    evaluation_id=evaluation.id,
                    plan_check_id=plan["id"],
                    name=plan["name"],
                    category=plan["category"],
                    tool=plan["tool"],
                    execution_mode="static",
                    status="running",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(check)
                db.add(AgentEvent(evaluation_id=evaluation.id, stage="EXECUTE", status="started", message=f"{plan['name']} started", metadata_json={"check_id": plan["id"]}))
                db.commit()

                arch_analysis = ArchitectureAnalyzer().analyze(db, evaluation.id, evaluation.snapshot_id, evaluation.snapshot.workspace_path)

                check.status = arch_analysis.status
                check.completed_at = datetime.now(timezone.utc)

                if arch_analysis.status == "completed":
                    # Import architecture findings into findings table
                    for af in arch_analysis.findings:
                        import hashlib
                        fp = "|".join(["architecture", af.rule_id, af.file_path, af.message])
                        fgp = hashlib.sha256(fp.encode("utf-8")).hexdigest()
                        db.add(Finding(
                            evaluation_id=evaluation.id,
                            check_id=plan["id"],
                            category="architecture",
                            tool="architecture-analyzer",
                            rule_id=af.rule_id,
                            severity=af.severity,
                            title=af.rule_id,
                            message=af.message,
                            file_path=af.file_path,
                            evidence=af.evidence,
                            fingerprint=fgp
                        ))
                elif arch_analysis.status == "failed":
                    errors = True

                db.flush()
                check.finding_count = db.query(Finding).filter(Finding.evaluation_id == evaluation.id, Finding.check_id == plan["id"]).count()
                db.add(AgentEvent(
                    evaluation_id=evaluation.id,
                    stage="COLLECT",
                    status="completed",
                    message=f"{plan['name']} {check.status}",
                    metadata_json={"check_id": plan["id"], "finding_count": check.finding_count}
                ))
                db.commit()

            elif plan["tool"] == "performance-analyzer" or plan.get("id") == "python-performance":
                check = EvaluationCheck(
                    evaluation_id=evaluation.id,
                    plan_check_id=plan["id"],
                    name=plan["name"],
                    category=plan["category"],
                    tool=plan["tool"],
                    execution_mode="static",
                    status="running",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(check)
                db.add(AgentEvent(evaluation_id=evaluation.id, stage="EXECUTE", status="started", message=f"{plan['name']} started", metadata_json={"check_id": plan["id"]}))
                db.commit()

                perf_analysis = PerformanceAnalyzer().analyze(db, evaluation.id, evaluation.snapshot_id, evaluation.snapshot.workspace_path)

                check.status = "completed" if perf_analysis else "failed"
                check.completed_at = datetime.now(timezone.utc)

                if perf_analysis:
                    for pf in perf_analysis.findings:
                        import hashlib
                        fp = "|".join(["performance", pf.rule, pf.file_path, str(pf.line), pf.message])
                        fgp = hashlib.sha256(fp.encode("utf-8")).hexdigest()
                        db.add(Finding(
                            evaluation_id=evaluation.id,
                            check_id=plan["id"],
                            category="performance",
                            tool="performance-analyzer",
                            rule_id=pf.rule,
                            severity=pf.severity,
                            title=pf.rule,
                            message=pf.message,
                            file_path=pf.file_path,
                            line_start=pf.line,
                            line_end=pf.line,
                            evidence=f"Penalty: -{pf.penalty}",
                            fingerprint=fgp
                        ))
                else:
                    errors = True

                db.flush()
                check.finding_count = db.query(Finding).filter(Finding.evaluation_id == evaluation.id, Finding.check_id == plan["id"]).count()
                db.add(AgentEvent(
                    evaluation_id=evaluation.id,
                    stage="COLLECT",
                    status="completed",
                    message=f"{plan['name']} {check.status}",
                    metadata_json={"check_id": plan["id"], "finding_count": check.finding_count}
                ))
                db.commit()

            elif exec_mode == "static":
                check = EvaluationCheck(
                    evaluation_id=evaluation.id,
                    plan_check_id=plan["id"],
                    name=plan["name"],
                    category=plan["category"],
                    tool=plan["tool"],
                    execution_mode="static",
                    status="running",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(check)
                db.add(AgentEvent(evaluation_id=evaluation.id, stage="EXECUTE", status="started", message=f"{plan['name']} started", metadata_json={"check_id": plan["id"]}))
                db.commit()

                adapter = ADAPTERS.get(plan["tool"])
                if adapter is None:
                    check.status = "skipped"
                    check.error_message = "no_adapter"
                elif plan["tool"] == "eslint":
                    check.status = "skipped"
                    check.error_message = "unsafe_repository_eslint_configuration"
                else:
                    result = adapter.execute(workspace)
                    check.status = result.status
                    check.error_message = result.error
                    check.duration_ms = result.duration_ms
                    if result.status == "completed":
                        for item in adapter.parse(result.output, workspace, plan):
                            db.add(Finding(evaluation_id=evaluation.id, check_id=plan["id"], **item))
                    else:
                        errors = True

                check.completed_at = datetime.now(timezone.utc)
                db.flush()
                check.finding_count = db.query(Finding).filter(Finding.evaluation_id == evaluation.id, Finding.check_id == plan["id"]).count()
                db.add(AgentEvent(
                    evaluation_id=evaluation.id,
                    stage="COLLECT",
                    status="completed",
                    message=f"{plan['name']} {check.status}",
                    metadata_json={"check_id": plan["id"], "finding_count": check.finding_count, "error": check.error_message}
                ))
                db.commit()

            elif plan["tool"] == "pytest" or plan.get("id") == "pytest-execution":
                check = EvaluationCheck(
                    evaluation_id=evaluation.id,
                    plan_check_id=plan["id"],
                    name=plan["name"],
                    category=plan["category"],
                    tool=plan["tool"],
                    execution_mode=exec_mode or "controlled_execution",
                    status="running",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(check)
                db.add(AgentEvent(evaluation_id=evaluation.id, stage="EXECUTE", status="started", message=f"{plan['name']} started", metadata_json={"check_id": plan["id"]}))
                db.commit()

                test_run = TestRunner().run_tests(db, evaluation.id, evaluation.snapshot_id, evaluation.snapshot.workspace_path)

                check.status = test_run.status
                check.duration_ms = test_run.duration_ms
                check.error_message = test_run.blocked_reason
                check.completed_at = datetime.now(timezone.utc)
                check.finding_count = test_run.tests_failed + test_run.tests_errors
                if test_run.status in ("execution_error", "timeout"):
                    errors = True

                db.add(AgentEvent(
                    evaluation_id=evaluation.id,
                    stage="COLLECT",
                    status="completed",
                    message=f"{plan['name']} {check.status}",
                    metadata_json={"check_id": plan["id"], "status": test_run.status, "passed": test_run.tests_passed, "failed": test_run.tests_failed}
                ))
                db.commit()

        evaluation.status = "completed_with_errors" if errors else "completed"
        db.add(AgentEvent(evaluation_id=evaluation.id, stage="REVIEW", status="completed", message="Evaluation completed", metadata_json={"status": evaluation.status}))
        db.commit()
        return evaluation
