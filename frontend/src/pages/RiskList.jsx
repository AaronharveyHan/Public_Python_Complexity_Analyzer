import React, { useState } from "react";
import { useTranslation } from "../i18n";
import { riskColor, ccColor } from "../utils/colors";

const TAB_STYLE = (active) => ({
  padding:      "8px 18px",
  background:   active ? "#2563eb" : "#141824",
  color:        active ? "#fff"    : "#94a3b8",
  border:       "1px solid #1e2536",
  borderRadius: 6,
  cursor:       "pointer",
  fontSize:     12,
  fontWeight:   active ? 600 : 400,
});

const INPUT_STYLE = {
  background: "#0f1117", border: "1px solid #2d3748",
  borderRadius: 6, padding: "7px 12px", color: "#e2e8f0",
  fontSize: 12, outline: "none", width: 220,
};

function Badge({ label, color }) {
  return (
    <span style={{
      background: `${color}22`, color,
      border: `1px solid ${color}44`,
      borderRadius: 4, fontSize: 10, padding: "1px 6px",
    }}>
      {label}
    </span>
  );
}

function matches(term, ...fields) {
  if (!term) return true;
  const q = term.toLowerCase();
  return fields.some((f) => f && String(f).toLowerCase().includes(q));
}

/* ── Function table ────────────────────────────────────────────────────── */
function FuncTable({ funcs, emptyMsg, search, t }) {
  const filtered = funcs.filter((fn) =>
    matches(search, fn.qualname, fn.file)
  );
  if (!filtered.length) {
    return <div style={{ color: "#64748b", textAlign: "center", padding: 32 }}>{emptyMsg}</div>;
  }
  const headers = [
    t("riskList.colFunction"), t("riskList.colFile"),
    t("riskList.colLine"),     t("riskList.colLoc"),
    t("riskList.colCc"),       t("riskList.colParams"),
    t("riskList.colFlags"),
  ];
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
      <thead>
        <tr style={{ color: "#64748b", textAlign: "left" }}>
          {headers.map((h) => (
            <th key={h} style={{ padding: "6px 10px", borderBottom: "1px solid #1e2536" }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {filtered.map((fn) => (
          <tr key={`${fn.file}::${fn.qualname}::${fn.line_start}`} style={{ borderBottom: "1px solid #1e2536" }}>
            <td style={{ padding: "8px 10px", color: "#e2e8f0", fontFamily: "monospace" }}>
              {fn.qualname}
            </td>
            <td style={{ padding: "8px 10px", color: "#60a5fa" }}>{fn.file}</td>
            <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{fn.line_start}</td>
            <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{fn.loc}</td>
            <td style={{ padding: "8px 10px", color: ccColor(fn.complexity) }}>{fn.complexity}</td>
            <td style={{ padding: "8px 10px", color: fn.is_many_params ? "#f97316" : "#94a3b8" }}>
              {fn.n_params ?? "–"}
            </td>
            <td style={{ padding: "8px 10px", display: "flex", gap: 4, flexWrap: "wrap" }}>
              {fn.is_high_complexity            && <Badge label={t("riskList.badgeHighCc")}     color="#ef4444" />}
              {fn.is_long                       && <Badge label={t("riskList.badgeLong")}       color="#f97316" />}
              {fn.is_duplicate                  && <Badge label={t("riskList.badgeDup")}        color="#d97706" />}
              {fn.is_many_params                && <Badge label={t("riskList.badgeManyParams")} color="#8b5cf6" />}
              {fn.annotation_coverage === 0     && <Badge label={t("riskList.badgeNoTypes")}    color="#64748b" />}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ── File table ─────────────────────────────────────────────────────────── */
function FileTable({ files, emptyMsg, search, t }) {
  const filtered = files.filter((f) =>
    matches(search, f.relative_path, f.path)
  );
  if (!filtered.length) {
    return <div style={{ color: "#64748b", textAlign: "center", padding: 32 }}>{emptyMsg}</div>;
  }
  const headers = [
    t("riskList.colModule"), t("riskList.colLoc"),    t("riskList.colSloc"),
    t("riskList.colFns"),    t("riskList.colAvgCc"),  t("riskList.colMaxCc"),
    t("riskList.colRisk"),   t("riskList.colGrade"),
  ];
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
      <thead>
        <tr style={{ color: "#64748b", textAlign: "left" }}>
          {headers.map((h) => (
            <th key={h} style={{ padding: "6px 10px", borderBottom: "1px solid #1e2536" }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {filtered.map((f) => (
          <tr key={f.relative_path || f.path} style={{ borderBottom: "1px solid #1e2536" }}>
            <td style={{ padding: "8px 10px", color: "#60a5fa" }}>{f.relative_path || f.path}</td>
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
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ── No Types table ─────────────────────────────────────────────────────── */
function NoTypesTable({ funcs, search, t }) {
  const sorted = [...funcs]
    .filter((fn) => fn.annotation_coverage === 0)
    .sort((a, b) => (b.n_params ?? 0) - (a.n_params ?? 0));
  const filtered = sorted.filter((fn) =>
    matches(search, fn.qualname, fn.file)
  );
  if (!filtered.length) {
    return <div style={{ color: "#64748b", textAlign: "center", padding: 32 }}>{t("riskList.emptyNoTypes")}</div>;
  }
  const headers = [
    t("riskList.colFunction"), t("riskList.colFile"),
    t("riskList.colLine"),     t("riskList.colParams"),
    t("riskList.colLoc"),
  ];
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
      <thead>
        <tr style={{ color: "#64748b", textAlign: "left" }}>
          {headers.map((h) => (
            <th key={h} style={{ padding: "6px 10px", borderBottom: "1px solid #1e2536" }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {filtered.map((fn) => (
          <tr key={`${fn.file}::${fn.qualname}::${fn.line_start}`} style={{ borderBottom: "1px solid #1e2536" }}>
            <td style={{ padding: "8px 10px", color: "#e2e8f0", fontFamily: "monospace" }}>{fn.qualname}</td>
            <td style={{ padding: "8px 10px", color: "#60a5fa" }}>{fn.file}</td>
            <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{fn.line_start}</td>
            <td style={{ padding: "8px 10px", color: fn.is_many_params ? "#f97316" : "#94a3b8" }}>
              {fn.n_params ?? "–"}
            </td>
            <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{fn.loc}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ── Duplicate table ────────────────────────────────────────────────────── */
function DupTable({ funcs, search, t }) {
  const filtered = funcs.filter((fn) =>
    matches(search, fn.qualname, fn.file, fn.duplicate_of)
  );
  if (!filtered.length) {
    return <div style={{ color: "#64748b", textAlign: "center", padding: 32 }}>{t("riskList.emptyDuplicates")}</div>;
  }
  const headers = [
    t("riskList.colFunction"), t("riskList.colFile"),
    t("riskList.colLine"),     t("riskList.colLoc"),
    t("riskList.colDuplicateOf"),
  ];
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
      <thead>
        <tr style={{ color: "#64748b", textAlign: "left" }}>
          {headers.map((h) => (
            <th key={h} style={{ padding: "6px 10px", borderBottom: "1px solid #1e2536" }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {filtered.map((fn) => (
          <tr key={`${fn.file}::${fn.qualname}::${fn.line_start}`} style={{ borderBottom: "1px solid #1e2536" }}>
            <td style={{ padding: "8px 10px", color: "#e2e8f0", fontFamily: "monospace" }}>{fn.qualname}</td>
            <td style={{ padding: "8px 10px", color: "#60a5fa" }}>{fn.file}</td>
            <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{fn.line_start}</td>
            <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{fn.loc}</td>
            <td style={{ padding: "8px 10px", color: "#d97706" }}>{fn.duplicate_of}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ── page ─────────────────────────────────────────────────────────────── */
export default function RiskList({ result }) {
  const { t } = useTranslation();
  const [tab,    setTab]    = useState(0);
  const [search, setSearch] = useState("");

  const topComplex = result?.top_complex_functions || [];
  const longFuncs  = result?.long_functions        || [];
  const largeFiles = result?.top_large_files       || [];
  const dups       = result?.duplicate_functions   || [];
  const allFuncs   = (result?.files || []).flatMap((f) => f.functions || []);
  const noTypeCount = allFuncs.filter((fn) => fn.annotation_coverage === 0).length;

  const TABS = [
    { label: t("riskList.tabComplex"),    count: topComplex.length },
    { label: t("riskList.tabLong"),       count: longFuncs.length  },
    { label: t("riskList.tabLarge"),      count: largeFiles.length },
    { label: t("riskList.tabDuplicates"), count: dups.length       },
    { label: t("riskList.tabNoTypes"),    count: noTypeCount        },
  ];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <h2 style={{ color: "#e2e8f0", margin: 0 }}>{t("riskList.title")}</h2>
        <input
          style={INPUT_STYLE}
          placeholder={t("riskList.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <p style={{ color: "#64748b", fontSize: 12, marginBottom: 20 }}>
        {t("riskList.subtitle")}
      </p>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {TABS.map(({ label, count }, i) => (
          <button key={label} onClick={() => setTab(i)} style={TAB_STYLE(tab === i)}>
            {label}&nbsp;<span style={{ opacity: .7 }}>({count})</span>
          </button>
        ))}
      </div>

      <div style={{ background: "#141824", border: "1px solid #1e2536", borderRadius: 8, overflow: "hidden" }}>
        {tab === 0 && <FuncTable   funcs={topComplex}  emptyMsg={t("riskList.emptyComplex")}    search={search} t={t} />}
        {tab === 1 && <FuncTable   funcs={longFuncs}   emptyMsg={t("riskList.emptyLong")}       search={search} t={t} />}
        {tab === 2 && <FileTable   files={largeFiles}  emptyMsg={t("riskList.emptyFiles")}      search={search} t={t} />}
        {tab === 3 && <DupTable    funcs={dups}                                                  search={search} t={t} />}
        {tab === 4 && <NoTypesTable funcs={allFuncs}                                             search={search} t={t} />}
      </div>
    </div>
  );
}
