"""Manual verification helper script for phase9-test.zip."""

import os
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app import config
from app.main import app

def test_manual_verification_phase9():
    zip_path = Path("../phase9-test.zip").resolve()
    assert zip_path.exists(), f"Zip file not found at {zip_path}"

    with patch.object(config, "ENABLE_LOCAL_TEST_EXECUTION", True):
        client = TestClient(app)
        with open(zip_path, "rb") as f:
            res = client.post("/api/projects", files={"file": ("phase9-test.zip", f.read(), "application/zip")})
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

        print("\n=== PHASE 9 MANUAL VERIFICATION REPORT ===")
        print("Scoring Version:", report["scoring_version"])
        print("Overall Score:", report["overall"]["score"])
        print("Assessment Coverage:", report["overall"]["measured_categories"], "/", report["overall"]["total_categories"])
        print("\nCategory Scores:")
        for cat in report["categories"]:
            print(f" - {cat['category']}: status={cat['status']}, score={cat['score']}")
            print(f"   Explanation: {cat['explanation']}")

        arch = report["architecture_analysis"]
        print("\nArchitecture Analysis:")
        print(" Status:", arch["status"])
        print(" Score:", arch["score"])
        print(" Metrics:", arch["metrics"])
        print(" Findings:")
        for f in arch["findings"]:
            print(f"  - [{f['rule_id']}] ({f['severity']}) {f['file_path']}: {f['message']}")

        test_run = report["test_run"]
        print("\nTest Execution:")
        print(" Status:", test_run["status"])
        print(" Collected:", test_run["tests_collected"])
        print(" Passed:", test_run["tests_passed"])
        print(" Failed:", test_run["tests_failed"])

        # Verification Assertions
        assert report["scoring_version"] == "1.2"
        assert report["overall"]["measured_categories"] == 5
        assert arch["metrics"]["circular_dependency_count"] == 1
        assert any(f["rule_id"] == "ARCH001" for f in arch["findings"])
        assert test_run["tests_collected"] == 3
        assert test_run["tests_passed"] == 3
