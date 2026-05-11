# Python Complexity Analyzer

A lightweight SonarQube-style complexity analysis + web visualization platform for Python projects.

## Features

| Feature | Detail |
|---------|--------|
| **LOC / SLOC** | Total, source-only, blank, comment lines per file |
| **Cyclomatic Complexity** | AST-based McCabe CC per function (no external deps) |
| **Function Analysis** | Count, avg/max length, long functions (≥50 lines) |
| **Dependency Graph** | Import-level directed graph with cycle detection |
| **Duplicate Detection** | AST body-hash comparison across all functions |
| **Risk Scoring** | Composite 0–100 score (CC + LOC + HCC ratio + dup ratio) |
| **FastAPI Backend** | REST + WebSocket real-time progress |
| **React + ECharts UI** | Treemap, force-directed graph, tables |
| **CLI** | Local or web-server mode |

---

## Quick Start

### 1. Install backend dependencies

```bash
pip install fastapi uvicorn networkx pydantic aiofiles
```

### 2. CLI – local analysis (no server needed)

```bash
# Summary report
python cli/analyze.py /path/to/project

# Save full JSON
python cli/analyze.py /path/to/project --output report.json

# Print raw JSON
python cli/analyze.py /path/to/project --json

# Ignore extra directories
python cli/analyze.py /path/to/project --ignore dist docs
```

Analysing **this project**:

```bash
python cli/analyze.py .
```

### 3. Web server + frontend

**Terminal 1 – API server**

```bash
uvicorn backend.api.main:app --reload --port 8000
```

**Terminal 2 – Frontend**

```bash
cd frontend
npm install
npm run dev        # → http://localhost:5173
```

Open [http://localhost:5173](http://localhost:5173), enter the project path, click **Analyze**.

### 4. CLI –web mode (starts server, opens browser hint)

```bash
python cli/analyze.py /path/to/project --web --port 8000
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/analyze` | Submit project path → returns `{task_id, status}` |
| GET  | `/result/{task_id}` | Poll result (status, progress, full JSON on completion) |
| GET  | `/tasks` | List all tasks |
| WS   | `/ws/{task_id}` | Real-time progress stream |
| GET  | `/health` | Health check |

**Submit example:**

```bash
curl -X POST http://localhost:8000/analyze \
     -H "Content-Type: application/json" \
     -d '{"project_path": "/home/user/Claude_Code"}'
```

**Result example:**

```bash
curl http://localhost:8000/result/<task_id>
```

---

## Project Structure

```
backend/
  analyzer/
    core.py          # Main orchestrator
    metrics.py       # LOC / SLOC counting
    complexity.py    # AST cyclomatic complexity
    functions.py     # Function extraction + duplicate detection
    dependencies.py  # Import graph + cycle detection (networkx)
    risk.py          # Risk scoring (0–100)
  api/
    main.py          # FastAPI app (REST + WebSocket)
    models.py        # Pydantic models
    tasks.py         # Background task runner + WS subscriptions

frontend/
  src/
    App.jsx                    # Root: start form → progress → pages
    pages/
      Dashboard.jsx            # KPI cards + treemap + CC distribution
      DependencyGraph.jsx      # Force-directed graph (ECharts)
      ModuleAnalysis.jsx       # Searchable/sortable module table + detail
      RiskList.jsx             # Top-N complex, long, large, duplicate
    components/
      Layout.jsx               # Sidebar nav
      MetricCard.jsx           # KPI card

cli/
  analyze.py                   # CLI entry point

requirements_analyzer.txt      # Backend deps
```

---

## Visualization Pages

### Dashboard
- **Risk Treemap** — each module is a tile; **area = LOC**, **color = risk level** (green → red)
- **CC Distribution bar chart** — how many functions fall in each complexity bucket
- **Top Risky Modules table**

### Dependency Graph
- **Force-directed graph** — drag, zoom, highlight neighbours on click
- **Red nodes/edges** = in a circular dependency cycle
- Filter: "Project only" vs "All imports"

### Module Analysis
- Sortable/searchable table of all files
- Click any row → per-function complexity bar chart + import list

### Risk List
- **Complex Functions** — top 10 by CC
- **Long Functions** — all functions ≥ 50 lines
- **Large Files** — top 10 by LOC
- **Duplicates** — functions with identical normalized bodies

---

## Analysis Results — This Project (Claude_Code)

```
Files:           41
LOC:         11,082
SLOC:         9,714
Functions:      526
Avg CC:         3.32
Max CC:           32  (analyze_project in backend/analyzer/core.py)
High-CC funcs:    24
Long funcs:       27
Duplicates:       55  (10.5%)
Cycles:            0
Risk Score:     25.8 / 100  (Grade B)
```

---

## Risk Score Formula

```
risk = 0.40 × (avg_cc / max_avg_cc × 100)
     + 0.30 × (loc / max_loc × 100)
     + 0.20 × (high_cc_functions / total_functions × 100)
     + 0.10 × (duplicate_functions / total_functions × 100)
```

Grade: A (<20) · B (<40) · C (<60) · D (<80) · F (≥80)

---

## Ignored Directories (defaults)

`venv`, `.venv`, `env`, `.env`, `.git`, `__pycache__`, `.tox`, `.mypy_cache`,
`node_modules`, `dist`, `build`, `.pytest_cache`, `.eggs`, `*.egg-info`
