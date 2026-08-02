from app.services.scoring_engine import ScoringEngine, overall
from app.models import CategoryScore, Evaluation, Finding

def test_scoring_is_deterministic_and_unmeasured(db_session):
    evaluation=Evaluation(project_id="p", status="completed"); db_session.add(evaluation); db_session.flush()
    db_session.add(Finding(evaluation_id=evaluation.id,check_id="b",category="security",tool="bandit",rule_id="B1",severity="low",title="x",message="x",file_path="a.py",fingerprint="x")); db_session.commit()
    engine = ScoringEngine()
    first = engine.score(db_session, evaluation)
    # score() deliberately deletes/recreates rows on a rerun. Snapshot plain
    # values before invoking it again; retaining the old ORM instances is invalid.
    first_values = [(x.category, x.score, x.status, x.scoring_version) for x in first]
    second = engine.score(db_session, evaluation)
    second_values = [(x.category, x.score, x.status, x.scoring_version) for x in second]
    assert first_values == second_values
    assert next(x for x in second if x.category=="security").score == 97
    assert next(x for x in second if x.category=="testing").score is None
    assert overall(second)["measured_categories"] == 2
    persisted = db_session.query(CategoryScore).filter(CategoryScore.evaluation_id == evaluation.id).all()
    assert len(persisted) == 6
    assert {score.category for score in persisted} == {"correctness", "security", "performance", "testing", "maintainability", "architecture"}
