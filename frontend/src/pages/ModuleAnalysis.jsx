import React, { useState, useMemo, useEffect } from "react";
import ReactECharts from "echarts-for-react";
import { useTranslation } from "../i18n";
import { riskColor, ccColor } from "../utils/colors";

/** Escape a value for safe insertion into an ECharts HTML tooltip. */
const escHtml = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

/* ── function bar for a module ────────────────────────────────────────── */
function FuncBar({ functions, t }) {
  if (!functions?.length) return <span style={{ color: "#64748b", fontSize: 12 }}>{t("moduleAnalysis.noFunctions")}</span>;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, maxHeight: 80, overflow: "hidden" }}>
      {functions.slice(0, 20).map((fn, i) => (
        <span
          key={i}
          title={`${fn.qualname}  CC:${fn.complexity}  LOC:${fn.loc}`}
          style={{
            fontSize: 10,
            background: fn.is_high_complexity ? "#7f1d1d" : fn.is_long ? "#422006" : "#1e2536",
            color:      fn.is_high_complexity ? "#fca5a5" : fn.is_long ? "#fdba74" : "#94a3b8",
            border:     fn.is_duplicate ? "1px solid #d97706" : "none",
            borderRadius: 3, padding: "2px 6px",
          }}
        >
          {fn.name}:{fn.complexity}
        </span>
      ))}
      {functions.length > 20 && (
        <span style={{ fontSize: 10, color: "#64748b" }}>
          {t("moduleAnalysis.more", { n: functions.length - 20 })}
        </span>
      )}
    </div>
  );
}

/* ── detail panel ─────────────────────────────────────────────────────── */
function ModuleDetail({ file, t }) {
  if (!file) return null;

  const ccOption = {
    backgroundColor: "transparent",
    grid:  { top: 10, bottom: 50, left: 40, right: 10 },
    xAxis: {
      type:      "category",
      data:      (file.functions || []).map((f) => f.name),
      axisLabel: { color: "#64748b", fontSize: 9, rotate: 45 },
      axisLine:  { lineStyle: { color: "#1e2536" } },
    },
    yAxis: {
      type:      "value",
      axisLabel: { color: "#64748b", fontSize: 10 },
      splitLine: { lineStyle: { color: "#1e2536" } },
    },
    tooltip: {
      trigger: "axis",
      formatter: (p) => {
        const fn = file.functions?.[p[0]?.dataIndex];
        return fn
          ? `<b>${escHtml(fn.qualname)}</b><br/>${t("moduleAnalysis.tooltipCc")} ${escHtml(fn.complexity)}<br/>${t("moduleAnalysis.tooltipLoc")} ${escHtml(fn.loc)}<br/>${t("moduleAnalysis.tooltipLine")} ${escHtml(fn.line_start)}`
          : "";
      },
    },
    series: [{
      type:     "bar",
      data:     (file.functions || []).map((fn) => ({
        value:     fn.complexity,
        itemStyle: { color: ccColor(fn.complexity) },
      })),
      barWidth: "60%",
    }],
  };

  const statRows = [
    [t("moduleAnalysis.detailLoc"),       file.loc],
    [t("moduleAnalysis.detailSloc"),      file.sloc],
    [t("moduleAnalysis.detailBlank"),     file.blank],
    [t("moduleAnalysis.detailComment"),   file.comment],
    [t("moduleAnalysis.detailFunctions"), file.n_functions],
    [t("moduleAnalysis.detailClasses"),   file.n_classes],
    [t("moduleAnalysis.detailAvgCc"),     file.complexity_avg],
    [t("moduleAnalysis.detailMaxCc"),     file.complexity_max],
    [t("moduleAnalysis.detailRisk"),      `${(file.risk_score||0).toFixed(1)} (${file.risk_grade})`],
  ];

  return (
    <div style={{ background: "#141824", border: "1px solid #2563eb", borderRadius: "0 0 8px 8px", padding: 20, borderTop: "none" }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: "#60a5fa", marginBottom: 12 }}>
        {file.relative_path}
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 10, marginBottom: 16 }}>
        {statRows.map(([l, v]) => (
          <div key={l} style={{ background: "#0f1117", borderRadius: 6, padding: "8px 12px" }}>
            <div style={{ fontSize: 10, color: "#64748b" }}>{l}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#e2e8f0" }}>{v}</div>
          </div>
        ))}
      </div>

      {/* Complexity per function */}
      {file.functions?.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>
            {t("moduleAnalysis.complexityPerFunc")}
          </div>
          <ReactECharts option={ccOption} style={{ height: 180 }} />
        </div>
      )}

      {/* Imports */}
      {file.imports?.length > 0 && (
        <div>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>
            {t("moduleAnalysis.imports", { n: file.imports.length })}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {file.imports.map((imp, i) => (
              <span key={i} style={{
                background: "#1e2536", color: "#a78bfa",
                borderRadius: 3, fontSize: 11, padding: "2px 8px",
              }}>{imp}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── numeric column keys for proper sort ─────────────────────────────── */
const NUMERIC_COLS = new Set(["loc","sloc","n_functions","complexity_avg","complexity_max","risk_score","annotation_rate"]);

/* ── page ─────────────────────────────────────────────────────────────── */
export default function ModuleAnalysis({ result }) {
  const { t } = useTranslation();
  const PAGE_SIZE = 50;
  const [search,       setSearch]       = useState("");
  const [sortKey,      setSortKey]      = useState("risk_score");
  const [sortAsc,      setSortAsc]      = useState(false);
  const [selected,     setSelected]     = useState(null);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const files = result?.files || [];

  const COLS = useMemo(() => [
    { key: "relative_path",  label: t("moduleAnalysis.colModule"),  w: "auto" },
    { key: "loc",            label: t("moduleAnalysis.colLoc"),     w: 70 },
    { key: "sloc",           label: t("moduleAnalysis.colSloc"),    w: 70 },
    { key: "n_functions",    label: t("moduleAnalysis.colFns"),     w: 55 },
    { key: "complexity_avg", label: t("moduleAnalysis.colAvgCc"),   w: 70 },
    { key: "complexity_max", label: t("moduleAnalysis.colMaxCc"),   w: 70 },
    { key: "risk_score",      label: t("moduleAnalysis.colRisk"),    w: 80 },
    { key: "risk_grade",      label: t("moduleAnalysis.colGrade"),   w: 55 },
    { key: "annotation_rate", label: t("moduleAnalysis.colAnnot"),   w: 70 },
  ], [t]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return [...files]
      .filter((f) => f.relative_path.toLowerCase().includes(q))
      .sort((a, b) => {
        const va = a[sortKey] ?? "";
        const vb = b[sortKey] ?? "";
        if (NUMERIC_COLS.has(sortKey)) {
          return sortAsc ? Number(va) - Number(vb) : Number(vb) - Number(va);
        }
        if (va < vb) return sortAsc ? -1 : 1;
        if (va > vb) return sortAsc ?  1 : -1;
        return 0;
      });
  }, [files, search, sortKey, sortAsc]);

  // Reset pagination when the filtered set changes
  useEffect(() => { setVisibleCount(PAGE_SIZE); }, [search, sortKey, sortAsc]);

  const toggleSort = (key) => {
    if (key === sortKey) setSortAsc((v) => !v);
    else { setSortKey(key); setSortAsc(false); }
  };

  const th = {
    padding: "6px 10px", textAlign: "left", fontSize: 11, color: "#64748b",
    cursor: "pointer", borderBottom: "1px solid #1e2536", userSelect: "none",
    whiteSpace: "nowrap",
  };

  return (
    <div>
      <h2 style={{ color: "#e2e8f0", marginBottom: 4 }}>{t("moduleAnalysis.title")}</h2>
      <p style={{ color: "#64748b", fontSize: 12, marginBottom: 16 }}>
        {t("moduleAnalysis.hint")}
      </p>

      {/* Search */}
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={t("moduleAnalysis.searchPlaceholder")}
        style={{
          background: "#141824", border: "1px solid #2d3748",
          borderRadius: 6, padding: "8px 14px", color: "#e2e8f0", fontSize: 13,
          outline: "none", width: 300, marginBottom: 12,
        }}
      />

      {/* Table */}
      <div style={{ background: "#141824", border: "1px solid #1e2536", borderRadius: 8, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key} style={{ ...th, width: c.w }} onClick={() => toggleSort(c.key)}>
                  {c.label} {sortKey === c.key ? (sortAsc ? "↑" : "↓") : ""}
                </th>
              ))}
              <th style={{ ...th, cursor: "default" }}>{t("moduleAnalysis.colFunctions")}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, visibleCount).map((f) => {
              const isSelected = selected?.relative_path === f.relative_path;
              return (
                <React.Fragment key={f.relative_path}>
                  <tr
                    onClick={() => setSelected(isSelected ? null : f)}
                    style={{
                      borderBottom: isSelected ? "none" : "1px solid #1e2536",
                      cursor: "pointer",
                      background: isSelected ? "rgba(37,99,235,.15)" : "transparent",
                    }}
                  >
                    <td style={{ padding: "8px 10px", color: "#60a5fa" }}>
                      <span style={{ marginRight: 6, fontSize: 10, color: "#64748b" }}>
                        {isSelected ? "▼" : "▶"}
                      </span>
                      {f.relative_path}
                    </td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{f.loc}</td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{f.sloc}</td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{f.n_functions}</td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{f.complexity_avg}</td>
                    <td style={{ padding: "8px 10px", color: f.complexity_max > 10 ? "#ef4444" : "#94a3b8" }}>
                      {f.complexity_max}
                    </td>
                    <td style={{ padding: "8px 10px", color: riskColor(f.risk_score || 0) }}>
                      {(f.risk_score || 0).toFixed(1)}
                    </td>
                    <td style={{ padding: "8px 10px", color: riskColor(f.risk_score || 0) }}>
                      {f.risk_grade || "–"}
                    </td>
                    <td style={{ padding: "8px 10px", color: f.annotation_rate == null ? "#64748b" : f.annotation_rate >= 0.8 ? "#22c55e" : f.annotation_rate >= 0.5 ? "#eab308" : "#f97316" }}>
                      {f.annotation_rate != null ? `${Math.round(f.annotation_rate * 100)}%` : "–"}
                    </td>
                    <td style={{ padding: "8px 10px" }}>
                      <FuncBar functions={f.functions} t={t} />
                    </td>
                  </tr>
                  {isSelected && (
                    <tr style={{ background: "rgba(37,99,235,.06)" }}>
                      <td
                        colSpan={COLS.length + 1}
                        style={{ padding: "0 0 8px 0", borderBottom: "1px solid #1e2536" }}
                      >
                        <ModuleDetail file={f} t={t} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 && (
        <div style={{ color: "#64748b", textAlign: "center", padding: 32 }}>
          {t("moduleAnalysis.noResults")}
        </div>
      )}

      {visibleCount < filtered.length && (
        <div style={{ textAlign: "center", marginTop: 12 }}>
          <button
            onClick={() => setVisibleCount((v) => v + PAGE_SIZE)}
            style={{
              background: "transparent", border: "1px solid #2d3748",
              color: "#94a3b8", borderRadius: 6, padding: "6px 20px",
              fontSize: 12, cursor: "pointer",
            }}
          >
            {t("moduleAnalysis.loadMore", { n: Math.min(PAGE_SIZE, filtered.length - visibleCount) })}
            &nbsp;
            <span style={{ opacity: 0.6 }}>
              ({filtered.length - visibleCount} {t("moduleAnalysis.remaining")})
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
