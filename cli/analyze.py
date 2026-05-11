#!/usr/bin/env python3
"""
Python Complexity Analyzer – CLI entry point.

Usage:
    python cli/analyze.py /path/to/project
    python cli/analyze.py /path/to/project --web
    python cli/analyze.py /path/to/project --web --port 8000
    python cli/analyze.py /path/to/project --json
    python cli/analyze.py /path/to/project --output report.json
    python cli/analyze.py /path/to/project --html report.html
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# ── ensure project root is in path ────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def _print_summary(result: dict) -> None:
    s = result.get("summary", {})
    name = result.get("project_name", "")
    print(f"\n{'='*60}")
    print(f"  📊 Analysis: {name}")
    print(f"{'='*60}")
    print(f"  Files          : {s.get('total_files', 0)}")
    print(f"  LOC            : {s.get('total_loc', 0):,}")
    print(f"  SLOC           : {s.get('total_sloc', 0):,}")
    print(f"  Functions      : {s.get('total_functions', 0)}")
    print(f"  Avg CC         : {s.get('avg_complexity', 0):.2f}")
    print(f"  Max CC         : {s.get('max_complexity', 0)}")
    print(f"  High-CC funcs  : {s.get('high_complexity_functions', 0)}")
    print(f"  Long funcs     : {s.get('long_functions', 0)}")
    print(f"  Duplicates     : {s.get('duplicate_functions', 0)}  ({s.get('duplicate_rate', 0)*100:.1f}%)")
    print(f"  Cycles         : {s.get('cycle_count', 0)}")
    print(f"  Risk Score     : {s.get('risk_score', 0):.1f} / 100")
    print(f"  Elapsed        : {s.get('elapsed_seconds', 0):.2f}s")

    top = result.get("top_complex_functions", [])
    if top:
        print(f"\n  Top complex functions:")
        for fn in top[:5]:
            print(f"    CC={fn['complexity']:3d}  {fn['file']}::{fn['qualname']}  (line {fn['line_start']})")

    cycles = result.get("dependency_graph", {}).get("cycles", [])
    if cycles:
        print(f"\n  ⚠  Circular dependencies ({len(cycles)}):")
        for c in cycles[:5]:
            print(f"    {' → '.join(c)}")

    print(f"{'='*60}\n")


def _run_local(project_path: str, output: str | None, as_json: bool,
               html_output: str | None, ignore_dirs: list[str] | None) -> None:
    """Run analysis locally (no server) and print / save results."""
    from backend.analyzer.core import analyze_project

    last_msg = [""]
    def progress(pct: int, msg: str) -> None:
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct:3d}%  {msg:<50}", end="", flush=True)
        last_msg[0] = msg

    result = analyze_project(
        project_path,
        ignore_dirs=set(ignore_dirs) if ignore_dirs else None,
        progress_cb=progress,
    )
    print()  # newline after progress

    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_summary(result)

    if output:
        Path(output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"  Results saved to: {output}")

    if html_output:
        from backend.api.report import generate_html_report
        Path(html_output).write_text(generate_html_report(result), encoding="utf-8")
        print(f"  HTML report saved to: {html_output}")


def _run_web(project_path: str, port: int, ignore_dirs: list[str] | None) -> None:
    """Start the FastAPI server and open the browser."""
    import uvicorn, threading, asyncio

    print(f"  Starting API server on http://localhost:{port} …")

    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": "backend.api.main:app", "host": "0.0.0.0", "port": port,
                "log_level": "warning"},
        daemon=True,
    )
    server_thread.start()

    # Wait until server is up (up to 10 s)
    import urllib.request as urlreq, urllib.error as urlerr, json as _json
    server_ready = False
    for _ in range(20):
        time.sleep(0.5)
        try:
            urlreq.urlopen(f"http://localhost:{port}/health", timeout=1)
            server_ready = True
            break
        except Exception:
            pass

    if not server_ready:
        print(f"\n  Error: server did not start after 10 s. "
              f"Is port {port} already in use?", file=sys.stderr)
        sys.exit(1)

    # Submit analysis
    body = _json.dumps({"project_path": project_path,
                        "ignore_dirs": ignore_dirs or []}).encode()
    req = urlreq.Request(
        f"http://localhost:{port}/analyze",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlreq.urlopen(req) as resp:
            task = _json.loads(resp.read())
    except urlerr.HTTPError as exc:
        body_bytes = exc.read()
        try:
            detail = _json.loads(body_bytes).get("detail", body_bytes.decode(errors="replace"))
        except Exception:
            detail = body_bytes.decode(errors="replace")
        print(f"\n  Error ({exc.code}): {detail}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n  Error: could not submit analysis: {exc}", file=sys.stderr)
        sys.exit(1)
    task_id = task["task_id"]
    print(f"  Analysis task: {task_id}")

    # Open browser
    frontend_url = f"http://localhost:5173"
    # Check if frontend dev server is already running; otherwise suggest npm run dev
    try:
        urllib.request.urlopen(frontend_url, timeout=1)
        webbrowser.open(frontend_url)
        print(f"  Browser opened: {frontend_url}")
    except Exception:
        print(f"\n  Frontend is not running. Start it with:")
        print(f"    cd frontend && npm install && npm run dev")
        print(f"\n  Or use the API directly:")
        print(f"    GET http://localhost:{port}/result/{task_id}")

    print(f"\n  API available at http://localhost:{port}")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\n  Stopped.")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Python Project Complexity Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("project_path", help="Path to the Python project to analyse")
    parser.add_argument("--web",    action="store_true", help="Start web server + open browser")
    parser.add_argument("--port",   type=int, default=8000, help="API server port (default: 8000)")
    parser.add_argument("--json",   action="store_true", help="Print result as JSON to stdout")
    parser.add_argument("--output", "-o", help="Save result JSON to file")
    parser.add_argument("--html",   help="Save self-contained HTML report to file")
    parser.add_argument("--ignore", nargs="*", default=None, help="Extra directories to ignore")
    args = parser.parse_args()

    path = str(Path(args.project_path).expanduser().resolve())
    if not Path(path).exists():
        print(f"Error: path not found: {path}", file=sys.stderr)
        sys.exit(1)

    if args.web:
        _run_web(path, args.port, args.ignore)
    else:
        _run_local(path, args.output, args.json, args.html, args.ignore)


if __name__ == "__main__":
    main()
