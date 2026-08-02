"""Manual verification helper script for phase10-test.zip."""

import io
from pathlib import Path
from unittest.mock import patch
import zipfile
from fastapi.testclient import TestClient

from app import config
from app.main import app


def create_phase10_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("app.py", "import services\n\ndef run_app():\n    unused_var = 123\n    return services.get_service_name()\n")
        zf.writestr("services.py", "import app\n\ndef get_service_name():\n    assert 1 == 1\n    return 'Phase10 Service'\n")
        zf.writestr("models.py", "class ItemModel:\n    def __init__(self, name: str):\n        self.name = name\n")
        zf.writestr("performance.py", """import time

def process_file_data(file_list):
    for f in file_list:
        with open(f, 'r') as fp:
            data = fp.read()
    return True

def sort_numbers(numbers):
    for i in range(5):
        sorted_list = sorted(numbers)
    return sorted_list

def calculate_heavy(x, y):
    res1 = calculate_matrix(x, y)
    res2 = calculate_matrix(x, y)
    return res1 + res2

def calculate_matrix(x, y):
    return x * y + 10
""")
        zf.writestr("tests/test_main.py", """from app import run_app
from services import get_service_name
from performance import process_file_data, sort_numbers, calculate_heavy

def test_app():
    assert run_app() == "Phase10 Service"

def test_service():
    assert get_service_name() == "Phase10 Service"

def test_process_file_data(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello", encoding="utf-8")
    assert process_file_data([str(f)]) is True

def test_sort_numbers():
    assert sort_numbers([3, 1, 2]) == [1, 2, 3]

def test_calculate_heavy():
    assert calculate_heavy(2, 3) == 32
""")
    return buf.getvalue()


def test_manual_verification_phase10():
    zip_path = Path("../phase10-test.zip").resolve()
    if zip_path.exists():
        zip_bytes = zip_path.read_bytes()
    else:
        zip_bytes = create_phase10_zip()
        zip_path.write_bytes(zip_bytes)

    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        client = TestClient(app)
        res = client.post("/api/projects", files={"file": ("phase10-test.zip", zip_bytes, "application/zip")})
        assert res.status_code in (200, 201), res.text
        project_id = res.json()["project_id"]

        eval_res = client.post(f"/api/projects/{project_id}/evaluations")
        assert eval_res.status_code in (200, 201), eval_res.text
        eval_id = eval_res.json()["id"]

        run_res = client.post(f"/api/evaluations/{eval_id}/run")
        assert run_res.status_code == 200

        score_res = client.post(f"/api/evaluations/{eval_id}/score")
        assert score_res.status_code == 200

        report_res = client.get(f"/api/evaluations/{eval_id}/report")
        assert report_res.status_code == 200
        report = report_res.json()

        print("\n=== PHASE 10 MANUAL VERIFICATION REPORT ===")
        print("Scoring Version:", report["scoring_version"])
        print("Overall Score:", report["overall"]["score"])
        print("Assessment Coverage:", report["overall"]["measured_categories"], "/", report["overall"]["total_categories"])
        print("\nCategory Scores:")
        for cat in report["categories"]:
            print(f" - {cat['category']}: status={cat['status']}, score={cat['score']}")
            print(f"   Explanation: {cat['explanation']}")

        perf = report["performance_analysis"]
        print("\nPerformance Analysis:")
        print(" Score:", perf["score"])
        print(" Metrics:", perf["metrics"])
        print(" Findings:")
        for f in perf["findings"]:
            print(f"  - [{f['rule']}] ({f['severity']}) {f['file_path']}:{f['line']}: {f['message']} (penalty: -{f['penalty']})")

        # Verification Assertions
        assert report["scoring_version"] == "1.3"
        assert report["overall"]["measured_categories"] == 6
        assert report["overall"]["total_categories"] == 6
        
        scores_by_cat = {c["category"]: c["score"] for c in report["categories"]}
        print("Scores Dict:", scores_by_cat)
        assert scores_by_cat.get("performance") == 82
