"""Trusted, deterministic scoring rules for normalized static findings and Phase 8 test evidence."""

from collections import Counter
from sqlalchemy.orm import Session

from ..models import ArchitectureAnalysis, CategoryScore, Evaluation, Finding, PerformanceAnalysis, TestRun

SCORING_VERSION = "1.3"
CATEGORIES = ("correctness", "security", "performance", "testing", "maintainability", "architecture")
PENALTIES = {
    "security": {"critical": 25, "high": 15, "medium": 8, "low": 3, "info": 1},
    "maintainability": {"critical": 10, "high": 6, "medium": 4, "low": 2, "info": 1}
}
UNMEASURED = {
    "correctness": "No correctness scoring check has been executed.",
    "performance": "No performance scoring check has been executed.",
    "testing": "No safe test execution or coverage analysis has been performed for this evaluation.",
    "architecture": "No architecture scoring check has been executed."
}


class ScoringEngine:
    def score(self, db: Session, evaluation: Evaluation) -> list[CategoryScore]:
        db.query(CategoryScore).filter(CategoryScore.evaluation_id == evaluation.id).delete()
        findings = db.query(Finding).filter(Finding.evaluation_id == evaluation.id).all()
        test_run = db.query(TestRun).filter(TestRun.evaluation_id == evaluation.id).order_by(TestRun.created_at.desc()).first()
        arch_analysis = db.query(ArchitectureAnalysis).filter(ArchitectureAnalysis.evaluation_id == evaluation.id).order_by(ArchitectureAnalysis.created_at.desc()).first()
        perf_analysis = db.query(PerformanceAnalysis).filter(PerformanceAnalysis.evaluation_id == evaluation.id).order_by(PerformanceAnalysis.created_at.desc()).first()

        rows = []
        for category in CATEGORIES:
            if category in PENALTIES:
                selected = [f for f in findings if f.category == category]
                counts = Counter(f.severity for f in selected)
                penalty = sum(PENALTIES[category].get(level, 0) * count for level, count in counts.items())
                score_val = max(0, min(100, 100 - penalty))
                explanation = f"Started at 100. {len(selected)} findings detected. Penalty: {penalty} points. Final score: {score_val}."
                rows.append(CategoryScore(
                    evaluation_id=evaluation.id,
                    category=category,
                    status="measured",
                    score=score_val,
                    scoring_version=SCORING_VERSION,
                    explanation=explanation,
                    evidence_summary={"finding_count": len(selected), "severity_counts": dict(sorted(counts.items())), "penalty": penalty, "base_score": 100}
                ))

            elif category == "architecture":
                if arch_analysis is None or arch_analysis.status != "completed" or arch_analysis.score is None:
                    reason = arch_analysis.explanation if arch_analysis and arch_analysis.explanation else UNMEASURED["architecture"]
                    rows.append(CategoryScore(
                        evaluation_id=evaluation.id,
                        category=category,
                        status="not_measured",
                        score=None,
                        scoring_version=SCORING_VERSION,
                        explanation=reason,
                        evidence_summary={"finding_count": 0, "status": arch_analysis.status if arch_analysis else "not_run"}
                    ))
                else:
                    rows.append(CategoryScore(
                        evaluation_id=evaluation.id,
                        category=category,
                        status="measured",
                        score=arch_analysis.score,
                        scoring_version=SCORING_VERSION,
                        explanation=arch_analysis.explanation or "Architecture score based on static evidence.",
                        evidence_summary={
                            "source_file_count": arch_analysis.source_file_count,
                            "package_count": arch_analysis.package_count,
                            "module_count": arch_analysis.module_count,
                            "dependency_edge_count": arch_analysis.dependency_edge_count,
                            "circular_dependency_count": arch_analysis.circular_dependency_count,
                            "high_fan_out_count": arch_analysis.high_fan_out_count,
                            "largest_file_lines": arch_analysis.largest_file_lines,
                            "average_file_lines": arch_analysis.average_file_lines,
                            "architecture_docs_present": arch_analysis.architecture_docs_present
                        }
                    ))

            elif category == "performance":
                if perf_analysis is None or perf_analysis.score is None:
                    rows.append(CategoryScore(
                        evaluation_id=evaluation.id,
                        category=category,
                        status="not_measured",
                        score=None,
                        scoring_version=SCORING_VERSION,
                        explanation=UNMEASURED["performance"],
                        evidence_summary={"finding_count": 0, "status": "not_run"}
                    ))
                else:
                    perf_findings = [f for f in findings if f.category == "performance"]
                    total_penalty = 100 - perf_analysis.score
                    rows.append(CategoryScore(
                        evaluation_id=evaluation.id,
                        category=category,
                        status="measured",
                        score=perf_analysis.score,
                        scoring_version=SCORING_VERSION,
                        explanation=f"Started at 100. {len(perf_findings)} performance findings detected. Total penalties: {total_penalty}. Final score: {perf_analysis.score}.",
                        evidence_summary={
                            "functions": perf_analysis.functions,
                            "loops": perf_analysis.loops,
                            "nested_loops": perf_analysis.nested_loops,
                            "average_complexity": perf_analysis.average_complexity,
                            "db_queries": len([f for f in perf_findings if f.rule_id == "PERF003"]),
                            "large_functions": len([f for f in perf_findings if f.rule_id == "PERF008"]),
                            "benchmark_enabled": perf_analysis.benchmark_enabled,
                            "finding_count": len(perf_findings),
                            "penalty": total_penalty,
                            "base_score": 100
                        }
                    ))

            elif category == "correctness":
                if test_run is None or test_run.status != "completed":
                    reason = test_run.blocked_reason if test_run and test_run.blocked_reason else UNMEASURED["correctness"]
                    rows.append(CategoryScore(
                        evaluation_id=evaluation.id,
                        category=category,
                        status="not_measured",
                        score=None,
                        scoring_version=SCORING_VERSION,
                        explanation=reason,
                        evidence_summary={"finding_count": 0, "test_status": test_run.status if test_run else "not_run"}
                    ))
                else:
                    effective = test_run.tests_passed + test_run.tests_failed + test_run.tests_errors
                    if effective == 0:
                        rows.append(CategoryScore(
                            evaluation_id=evaluation.id,
                            category=category,
                            status="not_measured",
                            score=None,
                            scoring_version=SCORING_VERSION,
                            explanation="No effective tests were executed.",
                            evidence_summary={"tests_collected": test_run.tests_collected, "tests_passed": 0}
                        ))
                    else:
                        pass_ratio = test_run.tests_passed / effective
                        score_val = max(0, min(100, round(100 * pass_ratio)))
                        explanation = "Correctness based on available automated test evidence."
                        rows.append(CategoryScore(
                            evaluation_id=evaluation.id,
                            category=category,
                            status="measured",
                            score=score_val,
                            scoring_version=SCORING_VERSION,
                            explanation=explanation,
                            evidence_summary={
                                "effective_tests": effective,
                                "tests_passed": test_run.tests_passed,
                                "tests_failed": test_run.tests_failed,
                                "tests_errors": test_run.tests_errors,
                                "tests_skipped": test_run.tests_skipped,
                                "pass_ratio": pass_ratio
                            }
                        ))

            elif category == "testing":
                if test_run is None or test_run.status != "completed":
                    reason = test_run.blocked_reason if test_run and test_run.blocked_reason else UNMEASURED["testing"]
                    rows.append(CategoryScore(
                        evaluation_id=evaluation.id,
                        category=category,
                        status="not_measured",
                        score=None,
                        scoring_version=SCORING_VERSION,
                        explanation=reason,
                        evidence_summary={"finding_count": 0, "test_status": test_run.status if test_run else "not_run"}
                    ))
                elif test_run.tests_collected == 0:
                    rows.append(CategoryScore(
                        evaluation_id=evaluation.id,
                        category=category,
                        status="not_measured",
                        score=None,
                        scoring_version=SCORING_VERSION,
                        explanation="No automated tests discovered.",
                        evidence_summary={"tests_collected": 0}
                    ))
                else:
                    base_pts = 50
                    count = test_run.tests_collected
                    if count >= 20:
                        suite_pts = 10
                    elif count >= 10:
                        suite_pts = 8
                    elif count >= 5:
                        suite_pts = 5
                    elif count >= 1:
                        suite_pts = 2
                    else:
                        suite_pts = 0

                    if test_run.coverage_percent is not None:
                        coverage_pts = round(test_run.coverage_percent * 0.40)
                        score_val = max(0, min(100, base_pts + suite_pts + coverage_pts))
                        explanation = f"Testing score based on test execution evidence ({base_pts} pts), test suite evidence ({suite_pts} pts), and coverage ({test_run.coverage_percent}% -> {coverage_pts} pts)."
                        rows.append(CategoryScore(
                            evaluation_id=evaluation.id,
                            category=category,
                            status="measured",
                            score=score_val,
                            scoring_version=SCORING_VERSION,
                            explanation=explanation,
                            evidence_summary={
                                "tests_collected": count,
                                "coverage_percent": test_run.coverage_percent,
                                "base_points": base_pts,
                                "suite_points": suite_pts,
                                "coverage_points": coverage_pts
                            }
                        ))
                    else:
                        score_val = max(0, min(60, base_pts + suite_pts))
                        explanation = f"Testing score based on test execution evidence ({base_pts} pts) and test suite evidence ({suite_pts} pts). Score is limited to a maximum of 60 because coverage evidence is unavailable."
                        rows.append(CategoryScore(
                            evaluation_id=evaluation.id,
                            category=category,
                            status="measured",
                            score=score_val,
                            scoring_version=SCORING_VERSION,
                            explanation=explanation,
                            evidence_summary={
                                "tests_collected": count,
                                "coverage_percent": None,
                                "base_points": base_pts,
                                "suite_points": suite_pts,
                                "coverage_points": None,
                                "note": "Coverage evidence unavailable"
                            }
                        ))

            else:
                rows.append(CategoryScore(
                    evaluation_id=evaluation.id,
                    category=category,
                    status="not_measured",
                    score=None,
                    scoring_version=SCORING_VERSION,
                    explanation=UNMEASURED[category],
                    evidence_summary={"finding_count": 0}
                ))

        db.add_all(rows)
        db.commit()
        return rows


def overall(scores: list[CategoryScore]) -> dict:
    measured = [score.score for score in scores if score.status == "measured" and score.score is not None]
    return {
        "score": round(sum(measured) / len(measured)) if measured else None,
        "status": "measured" if measured else "not_measured",
        "measured_categories": len(measured),
        "total_categories": len(CATEGORIES)
    }
