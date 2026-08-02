"""Versioned, deterministic Phase 2 planning rules; no checks are executed here."""

from .project_detector import DetectionResult

PLANNER_VERSION = "1.0"


def _check(id: str, name: str, category: str, tool: str, reason: str, evidence: list[str], execution_mode: str = "static") -> dict:
    return {"id": id, "name": name, "category": category, "tool": tool, "reason": reason, "evidence": evidence, "execution_mode": execution_mode, "status": "planned"}


class EvaluationPlanner:
    version = PLANNER_VERSION

    def create_plan(self, profile: DetectionResult) -> list[dict]:
        checks: list[dict] = []
        language_evidence = profile.language_evidence
        if "Python" in profile.languages:
            evidence = language_evidence["Python"]
            checks.extend([
                _check("python-static-quality", "Python Static Quality Analysis", "maintainability", "ruff", "Python source files detected", evidence),
                _check("python-security", "Python Security Analysis", "security", "bandit", "Python source files detected", evidence),
                _check("python-architecture", "Python Architecture Analysis", "architecture", "architecture-analyzer", "Static architecture and dependency analysis planned", evidence, "static_only"),
                _check("python-performance", "Python Performance Analysis", "performance", "performance-analyzer", "Python source files detected", evidence, "static_only"),
            ])
        if "JavaScript" in profile.languages or "TypeScript" in profile.languages:
            evidence = language_evidence.get("JavaScript", []) + language_evidence.get("TypeScript", [])
            checks.append(_check("javascript-typescript-static-quality", "JavaScript/TypeScript Static Quality Analysis", "maintainability", "eslint", "JavaScript or TypeScript source files detected", evidence))
        if profile.manifest_files:
            checks.append(_check("dependency-analysis", "Dependency Analysis", "security", "dependency-scanner", "Dependency manifest or lockfile detected", profile.manifest_files))
        architecture = {"FastAPI": "fastapi", "Flask": "flask", "Django": "django", "React": "react", "Next.js": "nextjs", "Express": "express", "Vue": "vue", "Vite": "vite"}
        for framework in profile.frameworks:
            framework_name = framework["name"]
            if framework_name in architecture:
                checks.append(_check(f"{architecture[framework_name]}-architecture", f"{framework_name} Architecture Analysis", "architecture", "structure-rules", f"{framework_name} detected", [entry["file"] for entry in framework["evidence"]]))
        test_tools = {"pytest": "pytest", "unittest": "python-unittest", "Jest": "jest", "Vitest": "vitest"}
        for framework in profile.test_frameworks:
            name = framework["name"]
            if name in test_tools:
                name_display = "Python Test Execution" if name == "pytest" else f"{name} Evaluation"
                reason_text = "pytest tests detected" if name == "pytest" else f"{name} detected; execution requires a future sandbox"
                checks.append(_check(f"{test_tools[name]}-execution", name_display, "testing", test_tools[name], reason_text, [entry["file"] for entry in framework["evidence"]], "sandbox_required"))

        has_pytest_check = any(c["id"] == "pytest-execution" for c in checks)
        if not has_pytest_check and "Python" in profile.languages and profile.test_file_count > 0:
            checks.append(_check("pytest-execution", "Python Test Execution", "testing", "pytest", "Python test files detected", language_evidence.get("Python", []), "sandbox_required"))

        return checks
