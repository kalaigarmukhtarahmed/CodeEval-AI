import json
from app.services.static_analyzers import BanditAdapter, ESLintAdapter, RuffAdapter, fingerprint, relative_path, severity

def test_severity_fingerprint_and_safe_paths(tmp_path):
    assert severity("bandit", "HIGH") == "high"
    assert fingerprint("ruff", "F401", "a.py", 1, "x") == fingerprint("ruff", "F401", "a.py", 1, "x")
    assert relative_path(tmp_path, str(tmp_path / "a.py")) == "a.py"
    assert relative_path(tmp_path, "C:/outside.py") is None

def test_adapter_json_parsing(tmp_path):
    check={"category":"security"}; (tmp_path / "a.py").write_text("x")
    ruff=RuffAdapter().parse(json.dumps([{"filename":str(tmp_path / "a.py"),"code":"F401","message":"unused","location":{"row":1,"column":1},"end_location":{"row":1,"column":2}}]), tmp_path, check)
    bandit=BanditAdapter().parse(json.dumps({"results":[{"filename":str(tmp_path / "a.py"),"test_id":"B1","test_name":"issue","issue_text":"bad","issue_severity":"HIGH","line_number":1,"line_range":[1],"code":"x"}]}), tmp_path, check)
    eslint=ESLintAdapter().parse(json.dumps([{"filePath":str(tmp_path / "a.py"),"messages":[{"ruleId":"x","message":"bad","line":1,"column":1}]}]), tmp_path, check)
    assert ruff[0]["rule_id"] == "F401" and bandit[0]["severity"] == "high" and eslint[0]["tool"] == "eslint"

def test_persisted_string_workspace_path_is_safe_for_ruff_and_bandit(tmp_path):
    workspace = str(tmp_path); source = tmp_path / "app.py"; source.write_text("x")
    check = {"category": "security"}
    ruff = RuffAdapter().parse(json.dumps([{"filename": str(source), "code": "F401", "message": "unused", "location": {"row": 1}, "end_location": {"row": 1}}]), workspace, check)
    bandit = BanditAdapter().parse(json.dumps({"results": [{"filename": str(source), "test_id": "B1", "issue_text": "issue", "issue_severity": "LOW", "line_number": 1, "line_range": [1]}]}), workspace, check)
    assert ruff[0]["file_path"] == "app.py"
    assert bandit[0]["file_path"] == "app.py"

def test_string_workspace_path_rejects_outside_file(tmp_path):
    outside = tmp_path.parent / "outside.py"; outside.write_text("x")
    assert relative_path(str(tmp_path), str(outside)) is None
