from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str


class ProjectUploadResponse(BaseModel):
    project_id: str
    name: str
    status: str


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    created_at: datetime


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    snapshot_id: str | None
    status: str
    planner_version: str | None
    created_at: datetime


class ProfileResponse(BaseModel):
    evaluation_id: str
    total_source_files: int
    total_source_lines: int
    test_file_count: int
    languages: dict
    language_lines: dict
    frameworks: list
    package_managers: list
    test_frameworks: list
    test_directories: list
    manifest_files: list
    source_directories: list
    configuration_files: list


class PlanResponse(BaseModel):
    evaluation_id: str
    planner_version: str
    checks: list


class AgentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    stage: str
    status: str
    message: str
    metadata_json: dict | None
    created_at: datetime
