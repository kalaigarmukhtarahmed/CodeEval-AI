from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL, DATA_DIR, UPLOAD_DIR, WORKSPACE_DIR


DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database(bind_engine=None) -> None:
    """Create Phase 1-7 tables and perform idempotent SQLite column migrations for existing DBs."""
    target_engine = bind_engine or engine
    Base.metadata.create_all(bind=target_engine)

    url_str = str(target_engine.url)
    if not url_str.startswith("sqlite"):
        return

    inspector = inspect(target_engine)
    table_names = inspector.get_table_names()

    if "evaluations" in table_names:
        existing_columns = {column["name"] for column in inspector.get_columns("evaluations")}
        additions = {
            "snapshot_id": "VARCHAR(36)",
            "planner_version": "VARCHAR(32)",
            "plan_json": "JSON",
        }
        with target_engine.begin() as connection:
            for column, sql_type in additions.items():
                if column not in existing_columns:
                    connection.execute(text(f"ALTER TABLE evaluations ADD COLUMN {column} {sql_type}"))

    if "project_snapshots" in table_names:
        snapshot_columns = {column["name"] for column in inspector.get_columns("project_snapshots")}
        with target_engine.begin() as connection:
            for column in ("parent_snapshot_id", "derivation_type"):
                if column not in snapshot_columns:
                    connection.execute(text(f"ALTER TABLE project_snapshots ADD COLUMN {column} VARCHAR(36)"))

    if "fix_verifications" in table_names:
        with target_engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            pragma_info = connection.execute(text('PRAGMA table_info("fix_verifications")')).fetchall()
            # pragma_info tuple: (cid, name, type, notnull, dflt_value, pk)
            fix_id_info = next((col for col in pragma_info if col[1] == "fix_id"), None)
            batch_id_info = next((col for col in pragma_info if col[1] == "batch_id"), None)

            fix_id_is_not_null = fix_id_info is not None and fix_id_info[3] == 1
            batch_id_missing = batch_id_info is None

            if fix_id_is_not_null or batch_id_missing:
                connection.execute(text("ALTER TABLE fix_verifications RENAME TO fix_verifications_old"))

                connection.execute(text("""
                    CREATE TABLE fix_verifications (
                        id VARCHAR(36) NOT NULL PRIMARY KEY,
                        fix_id VARCHAR(36) NULL,
                        batch_id VARCHAR(36) NULL,
                        original_evaluation_id VARCHAR(36) NOT NULL,
                        verification_evaluation_id VARCHAR(36) NOT NULL,
                        original_snapshot_id VARCHAR(36) NOT NULL,
                        derived_snapshot_id VARCHAR(36) NOT NULL,
                        status VARCHAR(30) NOT NULL,
                        target_finding_status VARCHAR(30) NOT NULL,
                        resolved_count INTEGER NOT NULL DEFAULT 0,
                        remaining_count INTEGER NOT NULL DEFAULT 0,
                        new_count INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME NULL,
                        FOREIGN KEY(fix_id) REFERENCES fix_proposals (id),
                        FOREIGN KEY(batch_id) REFERENCES fix_batches (id),
                        FOREIGN KEY(original_evaluation_id) REFERENCES evaluations (id),
                        FOREIGN KEY(verification_evaluation_id) REFERENCES evaluations (id),
                        FOREIGN KEY(original_snapshot_id) REFERENCES project_snapshots (id),
                        FOREIGN KEY(derived_snapshot_id) REFERENCES project_snapshots (id)
                    )
                """))

                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fix_verifications_fix_id ON fix_verifications (fix_id)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fix_verifications_batch_id ON fix_verifications (batch_id)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fix_verifications_original_evaluation_id ON fix_verifications (original_evaluation_id)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fix_verifications_verification_evaluation_id ON fix_verifications (verification_evaluation_id)"))

                old_cols_info = connection.execute(text('PRAGMA table_info("fix_verifications_old")')).fetchall()
                old_col_names = [col[1] for col in old_cols_info]

                target_cols_info = connection.execute(text('PRAGMA table_info("fix_verifications")')).fetchall()
                target_col_names = [col[1] for col in target_cols_info]

                common_cols = [c for c in old_col_names if c in target_col_names]

                if common_cols:
                    cols_str = ", ".join(common_cols)
                    connection.execute(text(f"INSERT INTO fix_verifications ({cols_str}) SELECT {cols_str} FROM fix_verifications_old"))

                connection.execute(text("DROP TABLE fix_verifications_old"))
