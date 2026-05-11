"""
Self-contained HTML report generator.

Produces a single .html file with:
- Embedded CSS (light, print-friendly theme)
- All analysis data as inline JSON
- ECharts loaded from CDN for treemap + CC distribution charts
- Full tables for modules, functions, duplicates, cycles
"""
from __future__ import annotations

import html
import json
from datetime import datetime


# ── helpers ───────────────────────────────────────────────────────────────────

def _esc(v) -> str:
    return html.escape(str(v) if v is not None else "–")


def _risk_color(score: float) -> str:
    if score < 20: return "#16a34a"
    if score < 40: return "#65a30d"
    if score < 60: return "#ca8a04"
    if score < 80: return "#ea580c"
    return "#dc2626"


def _cc_color(cc: int) -> str:
    if cc <= 5:  return "#16a34a"
    if cc <= 10: return "#ca8a04"
    if cc <= 20: return "#ea580c"
    return "#dc2626"


def _grade_color(grade: str) -> str:
    return {"A": "#16a34a", "B": "#65a30d", "C": "#ca8a04",
            "D": "#ea580c", "F": "#dc2626"}.get(grade or "", "#6b7280")


def _grade(score: float) -> str:
    if score < 20: return "A"
    if score < 40: return "B"
    if score < 60: return "C"
    if score < 80: return "D"
    return "F"


def _kpi(label: str, value, color: str = "#1e293b", sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{_esc(sub)}</div>' if sub else ""
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{_esc(label)}</div>'
        f'<div class="kpi-value" style="color:{color}">{_esc(value)}</div>'
        f'{sub_html}</div>'
    )


def _badge(text: str, bg: str, fg: str) -> str:
    return (f'<span style="background:{bg};color:{fg};border:1px solid {fg}44;'
            f'border-radius:4px;font-size:10px;padding:1px 6px;margin:1px">'
            f'{_esc(text)}</span>')


# ── section builders ──────────────────────────────────────────────────────────

def _annot_color(rate) -> str:
    if rate is None:    return "#6b7280"
    if rate >= 0.8:     return "#16a34a"
    if rate >= 0.5:     return "#ca8a04"
    return "#ea580c"


def _func_table_rows(funcs: list[dict]) -> str:
    rows = []
    for fn in funcs:
        cc = fn.get("complexity", 0)
        flags = ""
        if fn.get("is_high_complexity"):
            flags += _badge("High CC",     "#fee2e2", "#dc2626")
        if fn.get("is_long"):
            flags += _badge("Long",        "#ffedd5", "#ea580c")
        if fn.get("is_duplicate"):
            flags += _badge("Dup",         "#fef3c7", "#d97706")
        if fn.get("is_many_params"):
            flags += _badge("Many Params", "#f3e8ff", "#7c3aed")
        if fn.get("annotation_coverage") == 0:
            flags += _badge("No Types",    "#f1f5f9", "#6b7280")
        n_params = fn.get("n_params", "")
        rows.append(
            f"<tr>"
            f'<td class="mono">{_esc(fn.get("qualname",""))}</td>'
            f'<td class="mono sm">{_esc(fn.get("file",""))}</td>'
            f'<td class="num">{fn.get("line_start","")}</td>'
            f'<td class="num">{fn.get("loc","")}</td>'
            f'<td class="num" style="color:{_cc_color(cc)};font-weight:700">{cc}</td>'
            f'<td class="num">{n_params}</td>'
            f"<td>{flags}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _module_table_rows(files: list[dict]) -> str:
    sorted_files = sorted(files, key=lambda f: f.get("risk_score", 0), reverse=True)
    rows = []
    for i, f in enumerate(sorted_files, 1):
        rs    = f.get("risk_score", 0)
        gr    = f.get("risk_grade", "–")
        cm    = f.get("complexity_max", 0)
        ar    = f.get("annotation_rate")
        ar_str = f"{round(ar * 100)}%" if ar is not None else "–"
        rows.append(
            f"<tr>"
            f'<td class="num dim">{i}</td>'
            f'<td class="mono sm">{_esc(f.get("relative_path",""))}</td>'
            f'<td class="num">{f.get("loc",0)}</td>'
            f'<td class="num">{f.get("sloc",0)}</td>'
            f'<td class="num">{f.get("n_functions",0)}</td>'
            f'<td class="num">{f.get("complexity_avg",0)}</td>'
            f'<td class="num" style="color:{"#dc2626" if cm > 10 else "#1e293b"}">{cm}</td>'
            f'<td class="num" style="color:{_risk_color(rs)};font-weight:700">{rs:.1f}</td>'
            f'<td>{_badge(gr, _grade_color(gr)+"22", _grade_color(gr))}</td>'
            f'<td class="num" style="color:{_annot_color(ar)}">{ar_str}</td>'
            f"</tr>"
        )
    return "\n".join(rows)


def _dup_table_rows(funcs: list[dict]) -> str:
    rows = []
    for fn in funcs:
        rows.append(
            f"<tr>"
            f'<td class="mono">{_esc(fn.get("qualname",""))}</td>'
            f'<td class="mono sm">{_esc(fn.get("file",""))}</td>'
            f'<td class="num">{fn.get("line_start","")}</td>'
            f'<td class="num">{fn.get("loc","")}</td>'
            f'<td class="mono sm" style="color:#d97706">{_esc(fn.get("duplicate_of",""))}</td>'
            f"</tr>"
        )
    return "\n".join(rows)


def _long_table_rows(funcs: list[dict]) -> str:
    rows = []
    for fn in funcs:
        cc = fn.get("complexity", 0)
        rows.append(
            f"<tr>"
            f'<td class="mono">{_esc(fn.get("qualname",""))}</td>'
            f'<td class="mono sm">{_esc(fn.get("file",""))}</td>'
            f'<td class="num">{fn.get("line_start","")}</td>'
            f'<td class="num" style="color:#ea580c;font-weight:700">{fn.get("loc","")}</td>'
            f'<td class="num" style="color:{_cc_color(cc)}">{cc}</td>'
            f"</tr>"
        )
    return "\n".join(rows)


# ── main entry point ──────────────────────────────────────────────────────────

def generate_html_report(result: dict) -> str:
    s            = result.get("summary", {})
    files        = result.get("files", [])
    top_funcs    = result.get("top_complex_functions", [])
    long_funcs   = result.get("long_functions", [])
    dup_funcs    = result.get("duplicate_functions", [])
    failed_files = result.get("failed_files", [])
    graph        = result.get("dependency_graph", {})
    cycles       = graph.get("cycles", [])
    project_name = result.get("project_name", "Project")
    project_path = result.get("project_path", "")
    gen_time     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    risk_score  = s.get("risk_score", 0) or 0
    grade       = _grade(risk_score)
    grade_color = _grade_color(grade)

    # ── KPI cards ──────────────────────────────────────────────────────────
    dup_rate  = s.get("duplicate_rate", 0) or 0
    annot_cov = s.get("annotation_coverage", 0) or 0
    kpi_html = "".join([
        _kpi("Risk Score",     f"{risk_score:.1f}",
             grade_color, f"Grade {grade}"),
        _kpi("Total Files",    s.get("total_files", 0),   "#2563eb"),
        _kpi("Total LOC",      f"{s.get('total_loc', 0):,}",  "#2563eb"),
        _kpi("Total SLOC",     f"{s.get('total_sloc', 0):,}", "#64748b"),
        _kpi("Functions",      s.get("total_functions", 0),   "#7c3aed"),
        _kpi("Avg CC",         s.get("avg_complexity", 0),
             "#dc2626" if (s.get("avg_complexity") or 0) > 10 else "#16a34a"),
        _kpi("Max CC",         s.get("max_complexity", 0),
             "#dc2626" if (s.get("max_complexity") or 0) > 10 else "#ca8a04"),
        _kpi("High-CC Funcs",  s.get("high_complexity_functions", 0), "#ea580c"),
        _kpi("Long Funcs",     s.get("long_functions", 0),             "#ca8a04"),
        _kpi("Duplicates",     s.get("duplicate_functions", 0),
             "#ea580c", f"{dup_rate*100:.1f}%"),
        _kpi("Type Coverage",  f"{round(annot_cov * 100)}%",
             _annot_color(annot_cov)),
        _kpi("Cycles",         s.get("cycle_count", 0),
             "#dc2626" if s.get("cycle_count") else "#16a34a"),
        _kpi("Elapsed",        f"{s.get('elapsed_seconds', 0):.2f}s", "#64748b"),
    ])

    # ── collect unannotated functions from all files ────────────────────────
    _all_fns: list[dict] = [
        fn for fi in files for fn in fi.get("functions", [])
        if fn.get("annotation_coverage") == 0
    ]
    _all_fns.sort(key=lambda f: f.get("n_params", 0), reverse=True)

    # ── optional sections ───────────────────────────────────────────────────
    cycles_section = ""
    if cycles:
        items = "".join(
            f'<div class="cycle-row">'
            f'{"&nbsp;→&nbsp;".join(_esc(n) for n in c)}'
            f"&nbsp;→&nbsp;{_esc(c[0])}</div>"
            for c in cycles
        )
        cycles_section = f"""
        <div class="section">
          <div class="section-title warn">⚠ Circular Dependencies ({len(cycles)})</div>
          {items}
        </div>"""

    dup_section = ""
    if dup_funcs:
        _DUP_LIMIT = 30
        _dup_shown = dup_funcs[:_DUP_LIMIT]
        _dup_note  = (
            f'<div class="truncation-note">Showing first {_DUP_LIMIT} of {len(dup_funcs)} duplicates</div>'
            if len(dup_funcs) > _DUP_LIMIT else ""
        )
        dup_section = f"""
        <div class="section">
          <div class="section-title">Duplicate Functions ({len(dup_funcs)})</div>
          <div class="table-wrap"><table>
            <thead><tr>
              <th>Function</th><th>File</th><th>Line</th><th>LOC</th><th>Duplicate of</th>
            </tr></thead>
            <tbody>{_dup_table_rows(_dup_shown)}</tbody>
          </table></div>
          {_dup_note}
        </div>"""

    long_section = ""
    if long_funcs:
        _LONG_LIMIT = 30
        _long_shown = long_funcs[:_LONG_LIMIT]
        _long_note  = (
            f'<div class="truncation-note">Showing first {_LONG_LIMIT} of {len(long_funcs)} functions</div>'
            if len(long_funcs) > _LONG_LIMIT else ""
        )
        long_section = f"""
        <div class="section">
          <div class="section-title">Long Functions ({len(long_funcs)})</div>
          <div class="table-wrap"><table>
            <thead><tr>
              <th>Function</th><th>File</th><th>Line</th><th>LOC</th><th>CC</th>
            </tr></thead>
            <tbody>{_long_table_rows(_long_shown)}</tbody>
          </table></div>
          {_long_note}
        </div>"""

    untyped_section = ""
    if _all_fns:
        _UT_LIMIT   = 30
        _ut_shown   = _all_fns[:_UT_LIMIT]
        _ut_note    = (
            f'<div class="truncation-note">Showing first {_UT_LIMIT} of {len(_all_fns)} functions</div>'
            if len(_all_fns) > _UT_LIMIT else ""
        )
        ut_rows = "\n".join(
            f"<tr>"
            f'<td class="mono">{_esc(fn.get("qualname",""))}</td>'
            f'<td class="mono sm">{_esc(fn.get("file",""))}</td>'
            f'<td class="num">{fn.get("line_start","")}</td>'
            f'<td class="num">{fn.get("n_params","")}</td>'
            f'<td class="num">{fn.get("loc","")}</td>'
            f"</tr>"
            for fn in _ut_shown
        )
        untyped_section = f"""
        <div class="section">
          <div class="section-title">Unannotated Functions ({len(_all_fns)})</div>
          <div class="table-wrap"><table>
            <thead><tr>
              <th>Function</th><th>File</th><th>Line</th><th>Params</th><th>LOC</th>
            </tr></thead>
            <tbody>{ut_rows}</tbody>
          </table></div>
          {_ut_note}
        </div>"""

    failed_section = ""
    if failed_files:
        rows = "".join(
            f'<tr>'
            f'<td class="mono sm">{_esc(f.get("path",""))}</td>'
            f'<td style="color:#dc2626;font-size:11px">{_esc(f.get("reason",""))}</td>'
            f'<td class="sm">{_esc(f.get("detail",""))}</td>'
            f'</tr>'
            for f in failed_files
        )
        failed_section = f"""
        <div class="section" style="border-color:#fca5a5">
          <div class="section-title warn">⚠ Skipped Files ({len(failed_files)})</div>
          <div class="table-wrap"><table>
            <thead><tr><th>File</th><th>Reason</th><th>Detail</th></tr></thead>
            <tbody>{rows}</tbody>
          </table></div>
        </div>"""

    # ── chart data (safe JSON embed) ────────────────────────────────────────
    chart_data = json.dumps({
        "files": [
            {"name": f.get("relative_path", ""),
             "value": f.get("loc", 0),
             "risk": f.get("risk_score", 0)}
            for f in files
        ],
        "ccBins": {
            "1":    sum(1 for fi in files for fn in fi.get("functions", []) if fn.get("complexity", 0) <= 1),
            "2-3":  sum(1 for fi in files for fn in fi.get("functions", []) if 2 <= fn.get("complexity", 0) <= 3),
            "4-6":  sum(1 for fi in files for fn in fi.get("functions", []) if 4 <= fn.get("complexity", 0) <= 6),
            "7-10": sum(1 for fi in files for fn in fi.get("functions", []) if 7 <= fn.get("complexity", 0) <= 10),
            "11+":  sum(1 for fi in files for fn in fi.get("functions", []) if fn.get("complexity", 0) > 10),
        },
    }, default=str).replace("</", "<\\/")

    # ── assemble HTML ───────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Complexity Report — {_esc(project_name)}</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f1f5f9; color: #1e293b; font-size: 14px; line-height: 1.5; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 28px 20px; }}

    /* ── header ── */
    .header {{ background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
               color: #fff; border-radius: 12px; padding: 28px 32px;
               margin-bottom: 20px; display: flex; justify-content: space-between;
               align-items: flex-start; gap: 16px; }}
    .project-name {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
    .project-path {{ font-size: 12px; color: #94a3b8; font-family: monospace;
                     word-break: break-all; }}
    .header-meta  {{ font-size: 12px; color: #94a3b8; margin-top: 12px; }}
    .grade-badge  {{ font-size: 36px; font-weight: 900; width: 72px; height: 72px;
                     border-radius: 12px; display: flex; align-items: center;
                     justify-content: center; flex-shrink: 0;
                     background: {grade_color}; color: #fff; }}

    /* ── KPI grid ── */
    .kpi-grid  {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px,1fr));
                  gap: 10px; margin-bottom: 20px; }}
    .kpi-card  {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
                  padding: 14px 16px; }}
    .kpi-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: .8px;
                  color: #64748b; margin-bottom: 4px; }}
    .kpi-value {{ font-size: 26px; font-weight: 700; line-height: 1.1; }}
    .kpi-sub   {{ font-size: 11px; color: #94a3b8; margin-top: 2px; }}

    /* ── sections ── */
    .section       {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
                      padding: 20px; margin-bottom: 16px; }}
    .section-title {{ font-size: 14px; font-weight: 700; color: #1e293b;
                      margin-bottom: 14px; }}
    .section-title.warn {{ color: #dc2626; }}
    .charts-row    {{ display: grid; grid-template-columns: 3fr 2fr; gap: 16px;
                      margin-bottom: 16px; }}

    /* ── tables ── */
    .table-wrap {{ overflow-x: auto; }}
    table       {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    thead th    {{ background: #f8fafc; padding: 7px 10px; text-align: left;
                   font-size: 11px; font-weight: 600; color: #64748b;
                   border-bottom: 1px solid #e2e8f0; white-space: nowrap; }}
    tbody td    {{ padding: 7px 10px; border-bottom: 1px solid #f1f5f9;
                   vertical-align: middle; }}
    tbody tr:last-child td {{ border-bottom: none; }}
    tbody tr:hover          {{ background: #f8fafc; }}
    td.mono     {{ font-family: "SFMono-Regular", Consolas, monospace; }}
    td.num      {{ text-align: right; }}
    td.sm       {{ font-size: 11px; color: #64748b; }}
    td.dim      {{ color: #94a3b8; font-weight: 600; }}

    /* ── cycles ── */
    .cycle-row {{ font-family: monospace; font-size: 12px; color: #dc2626;
                  padding: 4px 0; border-bottom: 1px solid #fee2e2; }}
    .cycle-row:last-child {{ border-bottom: none; }}

    /* ── truncation notice ── */
    .truncation-note {{ font-size: 11px; color: #94a3b8; margin-top: 8px; text-align: right; }}

    /* ── footer ── */
    .footer {{ text-align: center; font-size: 11px; color: #94a3b8; margin-top: 28px;
               padding-top: 16px; border-top: 1px solid #e2e8f0; }}

    /* ── print ── */
    @media print {{
      body        {{ background: #fff; }}
      .container  {{ padding: 0; max-width: 100%; }}
      .section, .kpi-card {{ break-inside: avoid; }}
      .charts-row {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div>
      <div class="project-name">🔬 {_esc(project_name)}</div>
      <div class="project-path">{_esc(project_path)}</div>
      <div class="header-meta">
        Risk Score: <strong>{risk_score:.1f} / 100</strong> &nbsp;·&nbsp;
        {_esc(s.get("total_files", 0))} files, {_esc(s.get("total_functions", 0))} functions &nbsp;·&nbsp;
        Generated {_esc(gen_time)}
      </div>
    </div>
    <div class="grade-badge">{_esc(grade)}</div>
  </div>

  <!-- KPIs -->
  <div class="kpi-grid">{kpi_html}</div>

  <!-- Charts -->
  <div class="charts-row">
    <div class="section">
      <div class="section-title">
        Risk Treemap
        <span style="font-weight:400;font-size:11px;color:#94a3b8">
          &nbsp; Area = LOC &nbsp;·&nbsp; Color = Risk
        </span>
      </div>
      <div id="chart-treemap" style="height:300px"></div>
    </div>
    <div class="section">
      <div class="section-title">Complexity Distribution</div>
      <div id="chart-cc" style="height:300px"></div>
    </div>
  </div>

  <!-- Top Complex Functions -->
  <div class="section">
    <div class="section-title">Top Complex Functions ({len(top_funcs)})</div>
    <div class="table-wrap"><table>
      <thead><tr>
        <th>Function</th><th>File</th><th>Line</th>
        <th>LOC</th><th>CC</th><th>Params</th><th>Flags</th>
      </tr></thead>
      <tbody>{_func_table_rows(top_funcs[:20])}</tbody>
    </table></div>
  </div>

  <!-- Module Analysis -->
  <div class="section">
    <div class="section-title">Module Analysis ({len(files)} files, sorted by risk)</div>
    <div class="table-wrap"><table>
      <thead><tr>
        <th>#</th><th>Module</th><th>LOC</th><th>SLOC</th><th>Fns</th>
        <th>Avg CC</th><th>Max CC</th><th>Risk</th><th>Grade</th><th>Annot.</th>
      </tr></thead>
      <tbody>{_module_table_rows(files)}</tbody>
    </table></div>
  </div>

  {cycles_section}
  {dup_section}
  {long_section}
  {untyped_section}
  {failed_section}

  <div class="footer">
    Generated by <strong>Python Complexity Analyzer</strong> &nbsp;·&nbsp; {_esc(gen_time)}
  </div>
</div>

<script>
(function() {{
  var DATA = {chart_data};

  // ── Risk Treemap ────────────────────────────────────────────────────────
  var treemapEl = document.getElementById("chart-treemap");
  if (treemapEl && typeof echarts !== "undefined") {{
    var tc = echarts.init(treemapEl);
    tc.setOption({{
      backgroundColor: "transparent",
      tooltip: {{
        formatter: function(p) {{
          var d = p.data;
          return "<b>" + d.name + "</b><br/>LOC: " + d.value +
                 "<br/>Risk: " + (d.risk || 0).toFixed(1);
        }}
      }},
      series: [{{
        type: "treemap",
        data: DATA.files.map(function(f) {{
          var r = f.risk || 0;
          var color = r < 20 ? "#16a34a" : r < 40 ? "#65a30d" :
                      r < 60 ? "#ca8a04" : r < 80 ? "#ea580c" : "#dc2626";
          return {{ name: f.name, value: f.value, risk: r,
                    itemStyle: {{ color: color }} }};
        }}),
        width: "100%", height: "100%", roam: false, nodeClick: false,
        breadcrumb: {{ show: false }},
        label: {{ show: true, fontSize: 10, color: "#fff",
                  formatter: function(p) {{
                    return p.data.name + "\\n" + "Risk:" + (p.data.risk||0).toFixed(0);
                  }} }}
      }}]
    }});
    window.addEventListener("resize", function() {{ tc.resize(); }});
  }}

  // ── CC Distribution ────────────────────────────────────────────────────
  var ccEl = document.getElementById("chart-cc");
  if (ccEl && typeof echarts !== "undefined") {{
    var cc = echarts.init(ccEl);
    var bins = DATA.ccBins;
    var cats = Object.keys(bins);
    var vals = Object.values(bins);
    var colors = ["#16a34a","#65a30d","#ca8a04","#ea580c","#dc2626"];
    cc.setOption({{
      backgroundColor: "transparent",
      grid: {{ top: 10, bottom: 30, left: 50, right: 10 }},
      xAxis: {{
        type: "category", data: cats,
        axisLabel: {{ color: "#64748b", fontSize: 11 }},
        axisLine:  {{ lineStyle: {{ color: "#e2e8f0" }} }}
      }},
      yAxis: {{
        type: "value",
        axisLabel: {{ color: "#64748b", fontSize: 11 }},
        splitLine: {{ lineStyle: {{ color: "#f1f5f9" }} }}
      }},
      tooltip: {{ trigger: "axis" }},
      series: [{{
        type: "bar", barWidth: "55%",
        data: vals.map(function(v, i) {{
          return {{ value: v, itemStyle: {{ color: colors[i] }} }};
        }})
      }}]
    }});
    window.addEventListener("resize", function() {{ cc.resize(); }});
  }}

  if (typeof echarts === "undefined") {{
    ["chart-treemap","chart-cc"].forEach(function(id) {{
      var el = document.getElementById(id);
      if (el) {{
        el.style.cssText = "display:flex;align-items:center;justify-content:center;" +
                           "color:#94a3b8;font-size:12px;height:80px;";
        el.textContent = "Charts require an internet connection (ECharts CDN).";
      }}
    }});
  }}
}})();
</script>
</body>
</html>"""
