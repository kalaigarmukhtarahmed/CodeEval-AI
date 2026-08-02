from io import BytesIO
import zipfile

from app.services.evaluation_planner import EvaluationPlanner, PLANNER_VERSION
from app.services.project_detector import ProjectDetector


def write_files(root, files):
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())


def make_zip(files):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def test_language_detection_and_percentages(tmp_path):
    write_files(tmp_path, {"app.py": "# comment\nprint('x')\n", "web.ts": "export const x = 1;\n", "page.html": "<main></main>\n", "site.css": "body {}\n", "data.json": '{"ok": true}\n'})
    result = ProjectDetector().inspect(tmp_path)
    assert result.languages == {"CSS": 20, "HTML": 20, "JSON": 20, "Python": 20, "TypeScript": 20}
    assert result.total_source_files == 5
    assert result.total_source_lines == 5


def test_ignored_binary_and_malformed_files_are_safe(tmp_path):
    write_files(tmp_path, {"src/app.py": "print('kept')\n", "node_modules/vendor.js": "const ignored = true;\n", "dist/app.js": "const ignored = true;\n", "binary.py": b"\x00\x01", "malformed.py": b"print('kept')\xff\n"})
    result = ProjectDetector().inspect(tmp_path)
    assert result.total_source_files == 2
    assert result.language_lines["Python"] == 2
    assert "JavaScript" not in result.languages


def test_framework_detection_requires_repository_evidence(tmp_path):
    write_files(tmp_path, {
        "requirements.txt": "fastapi==0.1\nflask\ndjango\n",
        "package.json": '{"dependencies":{"react":"1","next":"1","express":"1","vue":"1","vite":"1"}}',
    })
    result = ProjectDetector().inspect(tmp_path)
    detected = {item["name"] for item in result.frameworks}
    assert {"FastAPI", "Flask", "Django", "React", "Next.js", "Express", "Vue", "Vite"} == detected
    assert all(item["evidence"] for item in result.frameworks)


def test_package_manager_and_test_framework_detection(tmp_path):
    write_files(tmp_path, {"requirements.txt": "pytest\n", "pyproject.toml": "[tool.poetry]\nname='sample'\n", "poetry.lock": "", "package.json": '{"devDependencies":{"jest":"1","vitest":"1"}}', "yarn.lock": "", "pytest.ini": "[pytest]\n", "src/example.test.ts": "test('x', () => {})\n", "tests/test_unit.py": "import unittest\n"})
    result = ProjectDetector().inspect(tmp_path)
    assert {item["name"] for item in result.package_managers} == {"pip", "Poetry", "yarn"}
    assert {item["name"] for item in result.test_frameworks} == {"pytest", "unittest", "Jest", "Vitest"}
    assert result.test_file_count == 2
    assert "tests" in result.test_directories


def test_deterministic_planner_and_version(tmp_path):
    write_files(tmp_path, {"app.py": "from fastapi import FastAPI\n", "requirements.txt": "fastapi\npytest\n", "tests/test_app.py": "import pytest\n"})
    profile = ProjectDetector().inspect(tmp_path)
    planner = EvaluationPlanner()
    first, second = planner.create_plan(profile), planner.create_plan(profile)
    assert first == second
    assert planner.version == PLANNER_VERSION
    assert all(item["evidence"] and item["reason"] and item["status"] == "planned" for item in first)
    assert any(item["execution_mode"] == "sandbox_required" for item in first)


def test_profile_plan_and_timeline_api(client):
    archive = make_zip({"backend/main.py": "from fastapi import FastAPI\n", "requirements.txt": "fastapi\npytest\n", "tests/test_main.py": "import pytest\n"})
    upload = client.post("/api/projects", files={"file": ("api-project.zip", archive, "application/zip")})
    project_id = upload.json()["project_id"]
    started = client.post(f"/api/projects/{project_id}/evaluations")
    assert started.status_code == 201
    evaluation_id = started.json()["id"]
    profile = client.get(f"/api/evaluations/{evaluation_id}/profile")
    plan = client.get(f"/api/evaluations/{evaluation_id}/plan")
    timeline = client.get(f"/api/evaluations/{evaluation_id}/timeline")
    assert profile.status_code == plan.status_code == timeline.status_code == 200
    assert profile.json()["languages"]["Python"] == 100
    assert plan.json()["planner_version"] == "1.0"
    assert [event["message"] for event in timeline.json()] == ["Repository inspection started", "Repository inspection completed", "Technology stack detected", "Evaluation planning started", "Evaluation plan generated"]


def test_phase2_invalid_and_minimal_repositories(client):
    assert client.post("/api/projects/missing/evaluations").status_code == 404
    assert client.get("/api/evaluations/missing/profile").status_code == 404
    upload = client.post("/api/projects", files={"file": ("minimal.zip", make_zip({"README.md": "hello"}), "application/zip")})
    evaluation = client.post(f"/api/projects/{upload.json()['project_id']}/evaluations")
    assert evaluation.status_code == 201
    profile = client.get(f"/api/evaluations/{evaluation.json()['id']}/profile").json()
    assert profile["total_source_files"] == 0
    assert profile["languages"] == {}
