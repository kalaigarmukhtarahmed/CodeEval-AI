import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    snapshots: Mapped[list["ProjectSnapshot"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    archive_path: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    archive_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uncompressed_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    project: Mapped[Project] = relationship(back_populates="snapshots")
    parent_snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    derivation_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="snapshot")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("project_snapshots.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    planner_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plan_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    project: Mapped[Project] = relationship(back_populates="evaluations")
    snapshot: Mapped[ProjectSnapshot | None] = relationship(back_populates="evaluations")
    agent_events: Mapped[list["AgentEvent"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")
    profile: Mapped["ProjectProfile | None"] = relationship(back_populates="evaluation", cascade="all, delete-orphan", uselist=False)
    checks: Mapped[list["EvaluationCheck"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")
    findings: Mapped[list["Finding"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")
    test_runs: Mapped[list["TestRun"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")
    architecture_analyses: Mapped[list["ArchitectureAnalysis"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")
    performance_analyses: Mapped[list["PerformanceAnalysis"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")


class EvaluationCheck(Base):
    __tablename__ = "evaluation_checks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    plan_check_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    tool: Mapped[str] = mapped_column(String(50), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation: Mapped[Evaluation] = relationship(back_populates="checks")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    check_id: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    tool: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    evaluation: Mapped[Evaluation] = relationship(back_populates="findings")


class CategoryScore(Base):
    __tablename__ = "category_scores"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scoring_version: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False); tool: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(100)); title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False); why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False); fixability: Mapped[str] = mapped_column(String(20), nullable=False)
    generation_method: Mapped[str] = mapped_column(String(50), nullable=False); status: Mapped[str] = mapped_column(String(30), nullable=False, default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class FixProposal(Base):
    __tablename__ = "fix_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False, index=True)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    source_snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False); status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed")
    original_content_hash: Mapped[str] = mapped_column(String(64), nullable=False); proposed_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    diff: Mapped[str] = mapped_column(Text, nullable=False); proposed_content: Mapped[str] = mapped_column(Text, nullable=False)
    generation_method: Mapped[str] = mapped_column(String(50), nullable=False); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    recommendation: Mapped[Recommendation] = relationship()


class FixBatch(Base):
    __tablename__ = "fix_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    source_snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=False, index=True)
    derived_snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed")
    fix_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    combined_diff: Mapped[str] = mapped_column(Text, nullable=False, default="")
    changes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    items: Mapped[list["FixBatchItem"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class FixBatchItem(Base):
    __tablename__ = "fix_batch_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("fix_batches.id"), nullable=False, index=True)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False, index=True)
    fix_proposal_id: Mapped[str] = mapped_column(ForeignKey("fix_proposals.id"), nullable=True, index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    batch: Mapped[FixBatch] = relationship(back_populates="items")
    recommendation: Mapped[Recommendation] = relationship()


class FixVerification(Base):
    __tablename__ = "fix_verifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fix_id: Mapped[str | None] = mapped_column(ForeignKey("fix_proposals.id"), nullable=True, index=True)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("fix_batches.id"), nullable=True, index=True)
    original_evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    verification_evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    original_snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=False)
    derived_snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    target_finding_status: Mapped[str] = mapped_column(String(30), nullable=False)
    resolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    fix: Mapped[FixProposal | None] = relationship()
    batch: Mapped[FixBatch | None] = relationship()


class ProjectProfile(Base):
    __tablename__ = "project_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=False, index=True)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, unique=True, index=True)
    total_source_files: Mapped[int] = mapped_column(Integer, nullable=False)
    total_source_lines: Mapped[int] = mapped_column(Integer, nullable=False)
    test_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    languages_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    language_lines_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    language_evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    frameworks_json: Mapped[list] = mapped_column(JSON, nullable=False)
    package_managers_json: Mapped[list] = mapped_column(JSON, nullable=False)
    test_frameworks_json: Mapped[list] = mapped_column(JSON, nullable=False)
    test_directories_json: Mapped[list] = mapped_column(JSON, nullable=False)
    manifest_files_json: Mapped[list] = mapped_column(JSON, nullable=False)
    source_directories_json: Mapped[list] = mapped_column(JSON, nullable=False)
    configuration_files_json: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    evaluation: Mapped[Evaluation] = relationship(back_populates="profile")


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    evaluation: Mapped[Evaluation] = relationship(back_populates="agent_events")


class TestRun(Base):
    __test__ = False
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(50), nullable=False, default="pytest")
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    tests_collected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coverage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="local_development")
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="test_runs")
    failures: Mapped[list["TestFailure"]] = relationship(back_populates="test_run", cascade="all, delete-orphan")


class TestFailure(Base):
    __test__ = False
    __tablename__ = "test_failures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    test_run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    failure_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    test_run: Mapped[TestRun] = relationship(back_populates="failures")


class ArchitectureAnalysis(Base):
    __test__ = False
    __tablename__ = "architecture_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed")
    source_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    package_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    module_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dependency_edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circular_dependency_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_fan_out_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    largest_file_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_file_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    architecture_docs_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="architecture_analyses")
    findings: Mapped[list["ArchitectureFinding"]] = relationship(back_populates="architecture_analysis", cascade="all, delete-orphan")


class ArchitectureFinding(Base):
    __test__ = False
    __tablename__ = "architecture_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    architecture_analysis_id: Mapped[str] = mapped_column(ForeignKey("architecture_analyses.id"), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="architecture")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    architecture_analysis: Mapped[ArchitectureAnalysis] = relationship(back_populates="findings")


class PerformanceAnalysis(Base):
    __test__ = False
    __tablename__ = "performance_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_snapshots.id"), nullable=False, index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    functions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loops: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nested_loops: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_complexity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    benchmark_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    benchmark_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    evaluation: Mapped[Evaluation] = relationship(back_populates="performance_analyses")
    findings: Mapped[list["PerformanceFinding"]] = relationship(back_populates="performance_analysis", cascade="all, delete-orphan")


class PerformanceFinding(Base):
    __test__ = False
    __tablename__ = "performance_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("performance_analyses.id"), nullable=False, index=True)
    rule: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    penalty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    performance_analysis: Mapped[PerformanceAnalysis] = relationship(back_populates="findings")


