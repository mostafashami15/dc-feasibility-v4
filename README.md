# DC Feasibility Tool v4

> Data center site feasibility analysis tool.
> Built by Mostafa (Metlen) with Claude AI assistance.

## Quick Start

### Backend (Python)

```bash
cd backend
source .venv/bin/activate   # On Mac/Linux
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend runs at: http://localhost:8000
API docs at: http://localhost:8000/docs

### Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173

## Project Structure

```
dc-feasibility-v4/
├── backend/          ← Python (FastAPI + calculation engine)
│   ├── engine/       ← Pure calculation — ZERO UI dependency
│   ├── api/          ← HTTP endpoints
│   ├── export/       ← Report generation (HTML, PDF, Excel)
│   └── tests/        ← Unit tests
├── frontend/         ← React + TypeScript UI
└── docs/             ← Project documentation
```

## Documentation

- [Architecture Agreement](./docs/ARCHITECTURE.md) — All technical decisions
- [Handbook](./docs/HANDBOOK.md) — Technical reference: assumptions, formulas, engine models, overrides
- [Changelog](./docs/CHANGELOG.md) — Version history
- [Completed Features](./docs/COMPLETED_FEATURES.md) — Archive of implemented feature plans

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 + FastAPI |
| Frontend | React 18 + TypeScript + Vite |
| Charts | Recharts (in-app) + Plotly.js (reports) |
| Styling | Tailwind CSS |
| Maps | Leaflet.js |
| Reports | Jinja2 HTML → PDF (weasyprint) + Excel (openpyxl) |
