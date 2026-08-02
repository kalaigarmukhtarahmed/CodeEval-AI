import hashlib
import re
import shutil
import uuid
from difflib import unified_diff
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ..models import Evaluation, Finding, FixBatch, FixBatchItem, FixProposal, ProjectSnapshot, Recommendation

RULES = {
    "F401": ("Unused import", "Remove the unused import if it is genuinely unnecessary.", "Unused imports increase noise and may indicate stale code.", "automatic"),
    "B105": ("Possible hardcoded password", "Move the value outside source code into appropriate configuration.", "Hardcoded credentials can be exposed through source control or logs.", "manual"),
    "B602": ("subprocess with shell=True", "Avoid shell=True and use a fixed argument list where possible.", "Shell interpretation can become dangerous with untrusted content.", "manual"),
    "B404": ("subprocess import", "Review whether subprocess is required and constrain its usage.", "Process creation needs careful review.", "manual"),
    "B607": ("Partial executable path", "Use an explicit executable path where appropriate.", "Ambiguous executable resolution can be risky.", "manual"),
}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_file(workspace: str, relative: str) -> Path:
    try:
        root = Path(workspace).resolve()
        raw = root / relative
        if raw.is_symlink():
            raise ValueError
        target = raw.resolve()
        if Path(relative).is_absolute() or ".." in Path(relative).parts or not target.is_relative_to(root):
            raise ValueError
        return target
    except (OSError, ValueError):
        raise ValueError("Unsafe fix path.")


def extract_target_symbol(message: str | None) -> str | None:
    if not message:
        return None
    match = re.search(r"`([^`]+)`", message)
    if match:
        return match.group(1).split(".")[0]
    return None


def transform_import_line(line: str, target_symbol: str | None) -> str | None:
    """
    Given an import line, removes target_symbol if specified.
    Returns transformed line string, or None if the line becomes empty and should be removed.
    """
    newline = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
    code = line.rstrip("\r\n")
    indent_len = len(code) - len(code.lstrip())
    indent = code[:indent_len]
    stripped = code.strip()

    if not target_symbol:
        return None

    if stripped.startswith("import "):
        items_str = stripped[len("import "):]
        items = [item.strip() for item in items_str.split(",") if item.strip()]
        new_items = []
        for item in items:
            name = item.split()[0]
            if name != target_symbol and item != target_symbol:
                new_items.append(item)
        if not new_items:
            return None
        return indent + "import " + ", ".join(new_items) + newline

    elif stripped.startswith("from "):
        parts = stripped.split(" import ", 1)
        if len(parts) == 2:
            mod_part, items_str = parts
            items = [item.strip() for item in items_str.split(",") if item.strip()]
            new_items = []
            for item in items:
                name = item.split()[0]
                if name != target_symbol and item != target_symbol:
                    new_items.append(item)
            if not new_items:
                return None
            return indent + mod_part + " import " + ", ".join(new_items) + newline

    return None


class RecommendationEngine:
    def generate(self, db, evaluation):
        db.query(Recommendation).filter(Recommendation.evaluation_id == evaluation.id).delete()
        for f in evaluation.findings:
            title, action, why, fixability = RULES.get(
                f.rule_id,
                ("Manual review recommended", "Review this analyzer finding and apply an appropriate developer-approved change.", "This finding requires context-specific judgment.", "unsupported")
            )
            db.add(Recommendation(
                evaluation_id=evaluation.id,
                finding_id=f.id,
                category=f.category,
                tool=f.tool,
                rule_id=f.rule_id,
                title=title,
                description=f.message,
                why_it_matters=why,
                recommended_action=action,
                fixability=fixability,
                generation_method="template-v1",
                status="generated"
            ))
        db.commit()
        return db.query(Recommendation).filter(Recommendation.evaluation_id == evaluation.id).all()

    def preview(self, db, recommendation, evaluation):
        if recommendation.fixability != "automatic" or recommendation.rule_id != "F401":
            raise ValueError("This recommendation requires a manual fix.")

        finding = next(f for f in evaluation.findings if f.id == recommendation.finding_id)
        path = safe_file(evaluation.snapshot.workspace_path, finding.file_path)
        original = path.read_text(encoding="utf-8-sig")

        lines = original.splitlines(keepends=True)
        index = (finding.line_start or 1) - 1

        if index < 0 or index >= len(lines):
            raise ValueError("Source changed since finding was generated.")

        target_line = lines[index]
        line_lstrip = target_line.lstrip()

        if not line_lstrip.startswith(("import ", "from ")):
            raise ValueError("Source changed since finding was generated.")

        target_symbol = extract_target_symbol(finding.message)
        if target_symbol and not re.search(r"\b" + re.escape(target_symbol) + r"\b", line_lstrip):
            raise ValueError("Source changed since finding was generated.")

        transformed = transform_import_line(target_line, target_symbol)
        if transformed is None:
            proposed_lines = lines[:index] + lines[index + 1:]
        else:
            proposed_lines = lines[:index] + [transformed] + lines[index + 1:]

        proposed = "".join(proposed_lines)
        diff = "".join(unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=finding.file_path,
            tofile=finding.file_path
        ))

        fix = FixProposal(
            recommendation_id=recommendation.id,
            evaluation_id=evaluation.id,
            source_snapshot_id=evaluation.snapshot_id,
            file_path=finding.file_path,
            original_content_hash=digest(original),
            proposed_content_hash=digest(proposed),
            diff=diff,
            proposed_content=proposed,
            generation_method="f401-line-removal"
        )
        db.add(fix)
        recommendation.status = "previewed"
        db.commit()
        db.refresh(fix)
        return fix

    def preview_batch(self, db: Session, evaluation_id: str, recommendation_ids: list[str]) -> FixBatch:
        evaluation = db.get(Evaluation, evaluation_id)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Evaluation not found.")

        if not recommendation_ids:
            raise HTTPException(status_code=400, detail="No recommendation IDs provided.")

        recs = db.query(Recommendation).filter(
            Recommendation.id.in_(recommendation_ids),
            Recommendation.evaluation_id == evaluation_id
        ).all()

        if len(recs) != len(set(recommendation_ids)):
            raise HTTPException(status_code=404, detail="One or more recommendations were not found for this evaluation.")

        # Validate fixability for all selected recommendations
        for r in recs:
            if r.fixability != "automatic" or r.rule_id != "F401":
                raise HTTPException(status_code=409, detail=f"Recommendation {r.id} ({r.rule_id}) is not eligible for automatic fix.")

        # Idempotency check: if identical batch exists, return it
        sorted_ids = sorted(recommendation_ids)
        existing_batches = db.query(FixBatch).filter_by(evaluation_id=evaluation_id).all()
        for b in existing_batches:
            b_ids = sorted([item.recommendation_id for item in b.items])
            if b_ids == sorted_ids:
                return b

        findings_map = {f.id: f for f in evaluation.findings}
        files_recs: dict[str, list[tuple[Recommendation, Finding]]] = {}
        for r in recs:
            finding = findings_map.get(r.finding_id)
            if not finding:
                raise HTTPException(status_code=404, detail=f"Finding for recommendation {r.id} not found.")
            files_recs.setdefault(finding.file_path, []).append((r, finding))

        changes = []
        all_diffs = []
        batch_items_data = []

        for file_path, items in files_recs.items():
            path = safe_file(evaluation.snapshot.workspace_path, file_path)
            original = path.read_text(encoding="utf-8-sig")
            original_hash = digest(original)
            lines = original.splitlines(keepends=True)

            items_sorted = sorted(items, key=lambda x: (x[1].line_start or 1), reverse=True)

            seen_lines = set()
            line_targets = []
            for r, f in items_sorted:
                idx = (f.line_start or 1) - 1
                if idx < 0 or idx >= len(lines):
                    raise HTTPException(status_code=409, detail="Source changed since findings were generated.")
                target_line = lines[idx]
                if not target_line.lstrip().startswith(("import ", "from ")):
                    raise HTTPException(status_code=409, detail="Source line is not an import statement.")

                target_symbol = extract_target_symbol(f.message)
                if idx in seen_lines:
                    raise HTTPException(status_code=409, detail="Selected fixes contain conflicting transformations.")
                seen_lines.add(idx)
                line_targets.append((idx, target_line, target_symbol, r))

            current_lines = list(lines)
            for idx, target_line, target_symbol, r in line_targets:
                transformed = transform_import_line(current_lines[idx], target_symbol)
                if transformed is None:
                    current_lines = current_lines[:idx] + current_lines[idx + 1:]
                else:
                    current_lines = current_lines[:idx] + [transformed] + current_lines[idx + 1:]

            proposed = "".join(current_lines)
            diff = "".join(unified_diff(
                original.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile=file_path,
                tofile=file_path
            ))

            changes.append({
                "file_path": file_path,
                "original_content_hash": original_hash,
                "proposed_content": proposed,
                "diff": diff,
                "recommendation_ids": [r.id for r, _ in items]
            })
            all_diffs.append(diff)

            for r, _ in items:
                batch_items_data.append({
                    "recommendation_id": r.id,
                    "file_path": file_path,
                    "original_content_hash": original_hash
                })

        combined_diff = "\n".join(all_diffs)

        batch = FixBatch(
            evaluation_id=evaluation.id,
            source_snapshot_id=evaluation.snapshot_id,
            status="proposed",
            fix_count=len(recs),
            files_changed_count=len(changes),
            combined_diff=combined_diff,
            changes_json=changes
        )
        db.add(batch)
        db.flush()

        for item_data in batch_items_data:
            db.add(FixBatchItem(
                batch_id=batch.id,
                recommendation_id=item_data["recommendation_id"],
                file_path=item_data["file_path"],
                original_content_hash=item_data["original_content_hash"]
            ))

        db.commit()
        db.refresh(batch)
        return batch

    def apply_batch(self, db: Session, batch_id: str) -> dict:
        batch = db.get(FixBatch, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Fix batch not found.")
        if batch.status != "proposed":
            raise HTTPException(status_code=409, detail="Fix batch is unavailable or has already been applied.")

        evaluation = db.get(Evaluation, batch.evaluation_id)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Evaluation not found.")

        # Stale preview protection: recalculate content hashes before applying
        for item in batch.items:
            source = safe_file(evaluation.snapshot.workspace_path, item.file_path)
            if digest(source.read_text(encoding="utf-8-sig")) != item.original_content_hash:
                raise HTTPException(status_code=409, detail="Source changed since batch preview was generated.")

        derived_path = Path(evaluation.snapshot.workspace_path).parent / f"derived-{uuid.uuid4()}"
        try:
            shutil.copytree(evaluation.snapshot.workspace_path, derived_path, symlinks=True)

            for change in batch.changes_json:
                target = safe_file(derived_path, change["file_path"])
                target.write_text(change["proposed_content"], encoding="utf-8")

            snapshot = ProjectSnapshot(
                project_id=evaluation.project_id,
                archive_path=evaluation.snapshot.archive_path,
                workspace_path=str(derived_path),
                archive_size_bytes=0,
                file_count=0,
                uncompressed_size_bytes=0,
                parent_snapshot_id=evaluation.snapshot_id,
                derivation_type="fix_batch"
            )
            db.add(snapshot)
            db.flush()
            batch.status = "applied"
            batch.derived_snapshot_id = snapshot.id

            for item in batch.items:
                rec = db.get(Recommendation, item.recommendation_id)
                if rec:
                    rec.status = "applied"

            db.commit()
            db.refresh(batch)

            return {
                "batch_id": batch.id,
                "status": "applied",
                "derived_snapshot_id": snapshot.id,
                "message": "Changes applied to derived snapshot. Verification pending."
            }

        except Exception as err:
            db.rollback()
            if derived_path.exists():
                shutil.rmtree(derived_path, ignore_errors=True)
            if isinstance(err, HTTPException):
                raise err
            raise HTTPException(status_code=500, detail=f"Failed to apply batch: {err}")
