# CodeEval AI

CodeEval AI is a hackathon MVP for uploading an untrusted software repository ZIP and preparing it for evidence-based, deterministic software-quality evaluation.

## Architecture

- `frontend/`: React, Vite, Tailwind dashboard.
- `backend/`: FastAPI, SQLAlchemy, SQLite API and secure upload pipeline.
- `docs/`: product and security documentation.
- `infra/`: future deployment assets.

Phase 1 creates project records, stores a validated archive outside public paths, and extracts it into a private workspace. Phase 2 safely detects the repository stack and creates a deterministic evaluation plan. It does not execute project code or evaluation tools.

## Development setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

For local uploads without reloads triggered by extracted repository files, use:

```powershell
uvicorn app.main:app --reload --reload-exclude "data/workspaces/*"
```

The API runs at `http://localhost:8000`; API documentation is at `/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173` and calls the local API by default.

## MVP limitations

Phase 3 produces evidence-backed static findings through controlled analyzers; it does not calculate scores, generate fixes, or re-evaluate code. See [static evaluation](docs/static-evaluation.md) and [findings](docs/findings-model.md).

Phase 4 adds deterministic scoring version 1.0 only for categories with executed evidence. See [scoring](docs/scoring.md) and the [evaluation report](docs/evaluation-report.md).

## Security statement

Repositories are untrusted input. The upload pipeline validates ZIP structure and extracts only into private temporary workspaces. It never executes uploaded code. See [docs/security-model.md](docs/security-model.md).
