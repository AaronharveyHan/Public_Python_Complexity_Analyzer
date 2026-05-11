import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import MetricCard from "../components/MetricCard";
import { useTranslation } from "../i18n";
import { riskColor, GRADE_COLOR } from "../utils/colors";

/** Escape a value for safe insertion into an ECharts HTML tooltip. */
const escHtml = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

/* ── treemap data ─────────────────────────────────────────────────────── */
function buildTreemap(files) {
  if (!files?.length) return [];
  return files.map((f) => ({
    name:      f.relative_path,
    value:     f.loc,
    itemStyle: { color: riskColor(f.risk_score || 0) },
    extra:     f,
  }));
}

/* ── complexity distribution ─────────────────────────────────────────── */
function buildCCDist(files) {
  const bins = { "1": 0, "2-3": 0, "4-6": 0, "7-10": 0, "11+": 0 };
  (files || []).forEach((f) =>
    (f.functions || []).forEach((fn) => {
      const cc = fn.complexity;
      if (cc <= 1)       bins["1"]++;
      else if (cc <= 3)  bins["2-3"]++;
      else if (cc <= 6)  bins["4-6"]++;
      else if (cc <= 10) bins["7-10"]++;
      else               bins["11+"]++;
    })
  );
  return { categories: Object.keys(bins), values: Object.values(bins) };
}

/* ── page ─────────────────────────────────────────────────────────────── */
export default function Dashboard({ result }) {
  const { t } = useTranslation();
  const s           = result?.summary || {};
  const treemapData = useMemo(() => buildTreemap(result?.files), [result]);
  const ccDist      = useMemo(() => buildCCDist(result?.files),  [result]);

  const treemapOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      formatter: (p) => {
        const f = p.data?.extra;
        if (!f) return escHtml(p.name);
        return [
          `<b>${escHtml(f.relative_path)}</b>`,
          `${t("dashboard.tooltipLoc")}: ${f.loc}  ${t("dashboard.tooltipSloc")}: ${f.sloc}`,
          `${t("dashboard.tooltipAvgCc")}: ${f.complexity_avg}  ${t("dashboard.tooltipMaxCc")}: ${f.complexity_max}`,
          `${t("dashboard.tooltipFunctions")}: ${f.n_functions}`,
          `${t("dashboard.tooltipRisk")}: ${f.risk_score?.toFixed(1)} (${escHtml(f.risk_grade)})`,
        ].join("<br/>");
      },
    },
    series: [{
      type:       "treemap",
      data:       treemapData,
      width:      "100%",
      height:     "100%",
      roam:       false,
      nodeClick:  false,
      breadcrumb: { show: false },
      label: {
        show:      true,
        formatter: (p) => {
          const f = p.data?.extra;
          return f ? `${f.relative_path}\nCC:${f.complexity_avg}  Risk:${f.risk_score?.toFixed(0)}` : p.name;
        },
        fontSize: 11,
        color:    "#fff",
      },
    }],
  }), [treemapData, t]);

  const ccOption = useMemo(() => ({
    backgroundColor: "transparent",
    grid: { top: 10, bottom: 30, left: 40, right: 10 },
    xAxis: {
      type:      "category",
      data:      ccDist.categories,
      axisLabel: { color: "#64748b", fontSize: 11 },
      axisLine:  { lineStyle: { color: "#1e2536" } },
    },
    yAxis: {
      type:      "value",
      axisLabel: { color: "#64748b", fontSize: 11 },
      splitLine: { lineStyle: { color: "#1e2536" } },
    },
    tooltip: { trigger: "axis" },
    series: [{
      type:     "bar",
      data:     ccDist.values.map((v, i) => ({
        value:     v,
        itemStyle: { color: ["#22c55e","#84cc16","#eab308","#f97316","#ef4444"][i] },
      })),
      barWidth: "50%",
    }],
  }), [ccDist]);

  const grade = s.risk_score < 20 ? "A"
              : s.risk_score < 40 ? "B"
              : s.risk_score < 60 ? "C"
              : s.risk_score < 80 ? "D" : "F";

  const legendItems = [
    [t("dashboard.low"),  "#22c55e"],
    [t("dashboard.med"),  "#eab308"],
    [t("dashboard.high"), "#f97316"],
    [t("dashboard.crit"), "#ef4444"],
  ];

  const topCols = [
    t("dashboard.colModule"), t("dashboard.colLoc"),
    t("dashboard.colAvgCc"),  t("dashboard.colMaxCc"),
    t("dashboard.colRisk"),   t("dashboard.colGrade"),
  ];

  return (
    <div>
      <h2 style={{ color: "#e2e8f0", marginBottom: 4 }}>
        {result?.project_name || "Project"} — {t("dashboard.title")}
      </h2>
      <p style={{ color: "#64748b", fontSize: 12, marginBottom: 24 }}>
        {result?.project_path}
      </p>

      {/* KPI cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12, marginBottom: 28 }}>
        <MetricCard label={t("dashboard.riskScore")}   value={s.risk_score ?? "–"}                          grade={grade} sub={`${t("dashboard.grade")} ${grade}`} />
        <MetricCard label={t("dashboard.totalFiles")}  value={s.total_files ?? "–"}                         color="#60a5fa" />
        <MetricCard label={t("dashboard.totalLoc")}    value={(s.total_loc ?? 0).toLocaleString()}           color="#60a5fa" />
        <MetricCard label={t("dashboard.totalSloc")}   value={(s.total_sloc ?? 0).toLocaleString()}          color="#94a3b8" />
        <MetricCard label={t("dashboard.functions")}   value={s.total_functions ?? "–"}                     color="#a78bfa" />
        <MetricCard label={t("dashboard.avgCc")}       value={s.avg_complexity ?? "–"}                      color={s.avg_complexity > 10 ? "#ef4444" : "#22c55e"} />
        <MetricCard label={t("dashboard.maxCc")}       value={s.max_complexity ?? "–"}                      color={s.max_complexity > 10 ? "#ef4444" : "#eab308"} />
        <MetricCard label={t("dashboard.highCcFuncs")} value={s.high_complexity_functions ?? "–"}           color="#f97316" />
        <MetricCard label={t("dashboard.longFuncs")}   value={s.long_functions ?? "–"}                      color="#eab308" />
        <MetricCard label={t("dashboard.duplicates")}  value={s.duplicate_functions ?? "–"}                 color="#f97316" sub={`${((s.duplicate_rate||0)*100).toFixed(1)}%`} />
        <MetricCard label={t("dashboard.cycles")}      value={s.cycle_count ?? "–"}                         color={s.cycle_count > 0 ? "#ef4444" : "#22c55e"} />
        <MetricCard label={t("dashboard.annotCoverage")} value={s.annotation_coverage != null ? `${Math.round(s.annotation_coverage * 100)}%` : "–"} color={s.annotation_coverage >= 0.8 ? "#22c55e" : s.annotation_coverage >= 0.5 ? "#eab308" : "#f97316"} />
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 24 }}>
        {/* Treemap */}
        <div style={{ background: "#141824", border: "1px solid #1e2536", borderRadius: 8, padding: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", marginBottom: 8 }}>
            {t("dashboard.riskTreemap")}&nbsp;
            <span style={{ fontSize: 11, color: "#64748b" }}>{t("dashboard.treemapSub")}</span>
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 8, fontSize: 11 }}>
            {legendItems.map(([l, c]) => (
              <span key={l} style={{ display: "flex", alignItems: "center", gap: 4, color: "#94a3b8" }}>
                <span style={{ width: 10, height: 10, background: c, borderRadius: 2, display: "inline-block" }} />
                {l}
              </span>
            ))}
          </div>
          <ReactECharts option={treemapOption} style={{ height: 340 }} notMerge />
        </div>

        {/* CC distribution */}
        <div style={{ background: "#141824", border: "1px solid #1e2536", borderRadius: 8, padding: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", marginBottom: 8 }}>
            {t("dashboard.complexityDist")}
          </div>
          <ReactECharts option={ccOption} style={{ height: 340 }} notMerge />
        </div>
      </div>

      {/* Top risky modules */}
      <div style={{ background: "#141824", border: "1px solid #1e2536", borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", marginBottom: 12 }}>
          {t("dashboard.topRiskyModules")}
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ color: "#64748b", textAlign: "left" }}>
              {topCols.map((h) => (
                <th key={h} style={{ padding: "4px 8px", borderBottom: "1px solid #1e2536" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...(result?.files || [])]
              .sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))
              .slice(0, 8)
              .map((f) => (
                <tr key={f.relative_path} style={{ borderBottom: "1px solid #1e2536" }}>
                  <td style={{ padding: "6px 8px", color: "#e2e8f0" }}>{f.relative_path}</td>
                  <td style={{ padding: "6px 8px", color: "#94a3b8" }}>{f.loc}</td>
                  <td style={{ padding: "6px 8px", color: "#94a3b8" }}>{f.complexity_avg}</td>
                  <td style={{ padding: "6px 8px", color: "#94a3b8" }}>{f.complexity_max}</td>
                  <td style={{ padding: "6px 8px", color: riskColor(f.risk_score) }}>
                    {(f.risk_score || 0).toFixed(1)}
                  </td>
                  <td style={{ padding: "6px 8px", color: GRADE_COLOR[f.risk_grade] || "#94a3b8" }}>
                    {f.risk_grade || "–"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
