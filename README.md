# Python Complexity Analyzer

A SonarQube-style code quality and complexity analysis platform for Python projects. Combines a Python analysis engine, a FastAPI backend, and a React frontend to deliver interactive visualizations of code metrics, dependency graphs, and risk scores.

## Features

- **Cyclomatic Complexity** — AST-based McCabe complexity per function, including `async for`, `match/case` (Python 3.10+)
- **Parameter Count** — Reports `n_params` per function; flags functions with more than 5 parameters (`is_many_params`)
- **LOC / SLOC Metrics** — Total, source, blank, and comment line counts per file
- **Function Analysis** — Count, average/max CC, long-function and high-CC classification
- **Duplicate Detection** — Finds logically identical functions via normalized body hashing (MD5)
- **Dependency Graph** — Import graph with circular-dependency detection (powered by NetworkX)
- **Risk Scoring** — Weighted 0–100 score with letter grades (A–F) per module and overall
- **Real-time Progress** — WebSocket streaming + HTTP polling during analysis
- **Task Timeout** — Analysis jobs exceeding the configured limit are cancelled and marked `failed`
- **Failed File Tracking** — Files that fail to parse (syntax errors, encoding issues) are listed separately instead of silently skipped
- **HTML Report Export** — Self-contained, print-ready HTML report with ECharts charts; downloadable via UI or `GET /report/{task_id}`
- **Rate Limiting** — Sliding-window rate limiter per IP (default: 10 requests / 60 s)
- **Interactive UI** — Treemap, force-directed graph, bar charts, sortable/searchable tables, inline row expansion
- **CLI Tool** — Standalone analysis with JSON or human-readable summary output
- **Path Security** — Server-side directory traversal protection via `ALLOWED_BASE_DIR`
- **CI** — GitHub Actions matrix across Python 3.10 / 3.11 / 3.12 with coverage gate (≥ 70 %)

## Architecture

```
Python_Complexity_Analyzer/
├── backend/
│   ├── analyzer/           # Core analysis engine
│   │   ├── core.py         # Main orchestrator (analyze_project)
│   │   ├── metrics.py      # LOC / SLOC counting, file collection
│   │   ├── complexity.py   # McCabe cyclomatic complexity (_CCVisitor)
│   │   ├── functions.py    # Function extraction & duplicate detection
│   │   ├── dependencies.py # Import graph & cycle detection
│   │   └── risk.py         # Risk scoring algorithm
│   └── api/                # FastAPI REST + WebSocket server
│       ├── main.py         # App, routes, CORS, rate limiter, path guard
│       ├── models.py       # Pydantic schemas + input validation
│       ├── report.py       # Self-contained HTML report generation
│       └── tasks.py        # Background task runner (ThreadPoolExecutor + watchdog)
├── cli/
│   └── analyze.py          # CLI entry point
├── frontend/               # React + Vite + ECharts
│   └── src/
│       ├── pages/          # Dashboard, DependencyGraph, ModuleAnalysis, RiskList
│       ├── components/     # Layout, MetricCard
│       ├── api/            # axios client (VITE_API_BASE configurable)
│       ├── i18n/           # English / Chinese translations
│       └── utils/          # Shared color helpers
└── tests/                  # pytest test suite (219 tests)
    ├── test_metrics.py
    ├── test_complexity.py
    ├── test_functions.py
    ├── test_dependencies.py
    ├── test_risk.py
    ├── test_core.py
    ├── test_api.py
    └── test_report.py
```

## Requirements

**Backend**

- Python 3.10+ (3.10 required for `match/case` complexity counting)
- `fastapi >= 0.100`
- `uvicorn`
- `networkx`
- `pydantic >= 2.0`

**Frontend**

- Node.js 18+
- npm

**Development / Testing**

- `pytest >= 7.0`
- `pytest-cov >= 4.0`
- `httpx`

## Installation

```bash
# Clone the repository
git clone https://github.com/aaronharveyhan/python_complexity_analyzer.git
cd Python_Complexity_Analyzer

# Install backend dependencies
pip install "fastapi>=0.100" "pydantic>=2.0" uvicorn networkx httpx

# Install frontend dependencies
cd frontend && npm install && cd ..
```

## Usage

### 1. CLI Mode (no server required)

```bash
# Human-readable summary
python cli/analyze.py /path/to/your/project

# Output full JSON to stdout
python cli/analyze.py /path/to/your/project --json

# Save JSON report to a file
python cli/analyze.py /path/to/your/project --output report.json

# Exclude additional directories (merged with built-in defaults)
python cli/analyze.py /path/to/your/project --ignore tests docs migrations
```

Sample output:

```
============================================================
  Analysis: my_project
============================================================
  Files          : 42
  LOC            : 8,301
  SLOC           : 5,920
  Functions      : 187
  Avg CC         : 2.41
  Max CC         : 18
  High-CC funcs  : 7
  Long funcs     : 3
  Duplicates     : 4  (2.1%)
  Cycles         : 1
  Risk Score     : 34.2 / 100
  Elapsed        : 0.38s
============================================================
```

### 2. Web UI Mode

```bash
# Terminal 1 — start the API server (must be run from the project root)
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — start the frontend dev server
cd frontend && npm run dev
```

Open [http://localhost:5173](http://localhost:5173), enter the **absolute server-side path** to a Python project, and click **Analyze**. The `/health` endpoint returns a `suggested_path` that pre-fills the input.

#### Windows / preview build

In PowerShell, set `VITE_API_BASE` so requests bypass the proxy and go directly to uvicorn:

```powershell
# From the frontend/ directory
$env:VITE_API_BASE = "http://127.0.0.1:8000"
npm run build
npm run preview       # served at http://localhost:4173
```

### 3. HTML Report Export

After an analysis completes, click **⬇ Export HTML** in the top-right corner of the UI, or download directly:

```bash
curl http://localhost:8000/report/<task_id> -o report.html
```

The report is a fully self-contained file (no external dependencies except the ECharts CDN) suitable for sharing or archiving.

### 4. Production Frontend Build

```bash
cd frontend
npm run build    # Optimized static files → dist/
npm run preview  # Test the production build locally (proxy included)
```

## Configuration

All thresholds and limits are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOWED_BASE_DIR` | `~` (home dir) | Root directory the server is allowed to analyse |
| `ALLOWED_ORIGINS` | localhost:5173/4173/3000 | Comma-separated CORS origins |
| `ANALYZE_RATE_LIMIT` | `10` | Max `/analyze` requests per IP per 60 s |
| `ANALYSIS_TIMEOUT` | `300` | Seconds before an analysis job is force-failed |
| `ANALYSIS_MAX_WORKERS` | CPU count | ThreadPoolExecutor worker threads |
| `LONG_FUNC_THRESHOLD` | `50` | Lines-of-code threshold for "long function" flag |
| `HIGH_CC_THRESHOLD` | `10` | CC threshold for "high complexity" flag |
| `MANY_PARAMS_THRESHOLD` | `5` | Parameter count threshold for "many params" flag |

## Security

### Path Traversal Protection

```bash
export ALLOWED_BASE_DIR=/srv/projects
uvicorn backend.api.main:app --port 8000
```

Paths outside `ALLOWED_BASE_DIR` receive HTTP **403 Forbidden**. The `ignore_dirs` field only accepts simple directory names (no `..`, `/`, or `\`).

### Rate Limiting

The `/analyze` endpoint enforces a sliding-window rate limit per client IP. Override the limit:

```bash
export ANALYZE_RATE_LIMIT=20   # allow 20 requests per 60 s
```

Excess requests receive HTTP **429 Too Many Requests**.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check — returns status, Python version, suggested path, allowed base |
| `POST` | `/analyze` | Submit a project path for analysis. Returns `{task_id, status}` immediately (HTTP 202) |
| `GET` | `/result/{task_id}` | Poll task status and retrieve full result once completed |
| `GET` | `/tasks` | List all submitted tasks |
| `GET` | `/report/{task_id}` | Download a self-contained HTML report for a completed task |
| `WS` | `/ws/{task_id}` | WebSocket stream for real-time progress updates |

**Submit analysis:**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/absolute/path/to/project", "ignore_dirs": ["tests"]}'
```

**Poll for result:**

```bash
curl http://localhost:8000/result/<task_id>
```

**Task status fields:**

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | UUID assigned at submission |
| `status` | `pending` \| `processing` \| `completed` \| `failed` | Current state |
| `progress` | 0–100 | Percentage complete |
| `message` | string | Current step description |
| `result` | object \| null | Full analysis payload (only when `completed`) |
| `error` | string \| null | Error message or traceback (only when `failed`) |

## Metrics Explained

### Cyclomatic Complexity (McCabe)

Computed by AST traversal of each function/method. Starts at 1 and adds 1 per decision point:

| Construct | Increment |
|-----------|-----------|
| `if` / `elif` | +1 |
| `for` / `async for` / `while` | +1 |
| `except` handler | +1 |
| Ternary expression (`x if c else y`) | +1 |
| Boolean `and` / `or` with N operands | +N−1 |
| Comprehension iteration | +1 |
| Comprehension filter (`if` clause) | +1 per clause |
| `match` statement (Python 3.10+) | +1 per `case` arm |

Functions are flagged **high complexity** when CC ≥ `HIGH_CC_THRESHOLD` (default 10).

### Parameter Count

`n_params` counts all parameter types: positional, positional-only, keyword-only, `*args`, and `**kwargs`. Functions with more than `MANY_PARAMS_THRESHOLD` (default 5) parameters are flagged with `is_many_params` and shown with a **"Many Params"** badge.

### Risk Score

A weighted composite score (0–100) per module:

```
risk = 0.40 × normalize(avg_cc,  lo=0, hi=max(project_max_cc, 10))
     + 0.30 × normalize(loc,     lo=0, hi=max(project_max_loc, 500))
     + 0.20 × (high_cc_functions / total_functions)  × 100
     + 0.10 × (duplicate_functions / total_functions) × 100
```

| Grade | Score |
|-------|-------|
| A | < 20 |
| B | 20 – 39 |
| C | 40 – 59 |
| D | 60 – 79 |
| F | ≥ 80 |

### Duplicate Detection

Functions longer than 5 lines are normalized (whitespace collapsed) and hashed with MD5. Functions that share the same hash across any files are flagged as duplicates. The first occurrence retains `is_duplicate=false`; subsequent ones are marked with `duplicate_of`.

### Default Ignored Directories

```
venv  .venv  env  .env  .git  __pycache__  .tox  .mypy_cache
node_modules  dist  build  .pytest_cache  .eggs  *.egg-info
```

Additional directories can be appended via `--ignore` (CLI) or the `ignore_dirs` field (API). Only simple directory names are accepted — path separators are rejected.

## Visualizations

| Page | Content | Notes |
|------|---------|-------|
| Dashboard | Risk treemap + CC histogram + top-module table | Area = LOC; color = risk score |
| Dependency Graph | Force-directed graph | Cycles highlighted red; filter project-only or all imports |
| Module Analysis | Sortable/searchable table | Click a row to expand an inline per-function CC bar chart |
| Risk List | Searchable tabbed lists | Complex functions, long functions, largest files, duplicates; Params column with Many-Params badge |

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov httpx

# Run the full suite
python -m pytest

# With coverage report
python -m pytest --cov=backend --cov-report=term-missing

# Enforce 70 % coverage gate (same as CI)
python -m pytest --cov=backend --cov-fail-under=70

# Single module
python -m pytest tests/test_complexity.py -v
```

The suite contains **219 tests** covering all backend modules and API endpoints.

| Test module | What it covers |
|-------------|----------------|
| `test_metrics.py` | `count_lines`, `collect_file_paths`, ignore-dir merging |
| `test_complexity.py` | `_CCVisitor` decision-point counting, `async for`, `match/case` |
| `test_functions.py` | `extract_functions`, `detect_duplicates`, param counting, hash stability |
| `test_dependencies.py` | `parse_imports`, `_module_id`, graph build, cycle detection |
| `test_risk.py` | `_normalize`, `_grade`, `compute_risk_scores`, floor-cap behavior |
| `test_core.py` | `analyze_project` end-to-end, progress callback, ignore dirs, failed files |
| `test_api.py` | `/health`, `/analyze`, `/result`, `/tasks`; 403/404/400/429 edge cases |
| `test_report.py` | HTML report generation, XSS escaping, KPI cards, table rows, truncation |

## CI

GitHub Actions runs the full test suite on every push to `main`, `feature/**`, and `claude/**` branches across Python 3.10, 3.11, and 3.12. Coverage must stay ≥ 70 % or the build fails. The coverage XML artifact is uploaded for the Python 3.11 run.

## License

MIT License — Copyright (c) 2026 AaronharveyHan
