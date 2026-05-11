import React, { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { useTranslation } from "../i18n";
import { riskColor } from "../utils/colors";

const KIND_COLOR = {
  project:     "#60a5fa",
  stdlib:      "#6b7280",
  third_party: "#a78bfa",
  unknown:     "#374151",
};

/** Escape a value for safe insertion into an ECharts HTML tooltip. */
const escHtml = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

/* ── build ECharts graph option ───────────────────────────────────────── */
function buildOption(graph, filter, t) {
  if (!graph) return {};

  const { nodes = [], edges = [], cycles = [] } = graph;
  const cycleNodeSet = new Set(cycles.flat());

  const visibleNodeIds = new Set(
    filter === "project"
      ? nodes.filter((n) => n.kind === "project").map((n) => n.id)
      : nodes.map((n) => n.id)
  );

  const eNodes = nodes
    .filter((n) => visibleNodeIds.has(n.id))
    .map((n) => ({
      id:         n.id,
      name:       n.id,
      symbolSize: n.kind === "project" ? 20 : 12,
      itemStyle: {
        color:       n.in_cycle ? "#ef4444" : (n.kind === "project" ? riskColor(n.risk) : KIND_COLOR[n.kind]),
        borderColor: n.in_cycle ? "#fca5a5" : "transparent",
        borderWidth: n.in_cycle ? 2 : 0,
      },
      label: { show: n.kind === "project", fontSize: 10, color: "#e2e8f0" },
    }));

  const eEdges = edges
    .filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target))
    .map((e) => ({
      source:    e.source,
      target:    e.target,
      lineStyle: {
        color:   e.in_cycle ? "#ef4444" : "#2d3748",
        width:   e.in_cycle ? 2 : 1,
        type:    e.in_cycle ? "solid" : "dashed",
        opacity: 0.8,
      },
    }));

  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        if (p.dataType === "node") {
          const n = nodes.find((x) => x.id === p.data?.id);
          if (!n) return escHtml(String(p.data?.id ?? ""));
          return [
            `<b>${escHtml(n.id)}</b>`,
            `${t("depGraph.tooltipKind")} ${escHtml(n.kind)}`,
            n.kind === "project" ? `${t("depGraph.tooltipRisk")} ${n.risk?.toFixed(1)}` : "",
            n.in_cycle ? `<span style='color:#ef4444'>${t("depGraph.tooltipInCycle")}</span>` : "",
          ].filter(Boolean).join("<br/>");
        }
        return `${escHtml(String(p.data?.source ?? ""))} → ${escHtml(String(p.data?.target ?? ""))}`;
      },
    },
    legend: {
      bottom: 10,
      data: ["project", "stdlib", "third_party"].map((k) => ({
        name:      k,
        icon:      "circle",
        itemStyle: { color: KIND_COLOR[k] },
      })),
      textStyle: { color: "#64748b", fontSize: 11 },
    },
    series: [{
      type:               "graph",
      layout:             "force",
      data:               eNodes,
      edges:              eEdges,
      roam:               true,
      draggable:          true,
      focusNodeAdjacency: true,
      force: {
        repulsion:  200,
        gravity:    0.05,
        edgeLength: [60, 160],
      },
      edgeSymbol:     ["none", "arrow"],
      edgeSymbolSize: 6,
    }],
  };
}

/* ── page ─────────────────────────────────────────────────────────────── */
export default function DependencyGraph({ result }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("project");
  const graph  = result?.dependency_graph;
  const option = useMemo(() => buildOption(graph, filter, t), [graph, filter, t]);

  const cycles    = graph?.cycles?.length  || 0;
  const nodeCount = graph?.nodes?.length   || 0;
  const edgeCount = graph?.edges?.length   || 0;

  const legendItems = [
    [t("depGraph.kindProject"),    "#60a5fa"],
    [t("depGraph.kindStdlib"),     "#6b7280"],
    [t("depGraph.kindThirdParty"), "#a78bfa"],
    [t("depGraph.kindCycle"),      "#ef4444"],
  ];

  return (
    <div>
      <h2 style={{ color: "#e2e8f0", marginBottom: 4 }}>{t("depGraph.title")}</h2>
      <p style={{ color: "#64748b", fontSize: 12, marginBottom: 20 }}>
        {t("depGraph.hint")}
      </p>

      {/* Stats bar */}
      <div style={{ display: "flex", gap: 16, marginBottom: 16, fontSize: 12, color: "#94a3b8" }}>
        <span>{t("depGraph.nodes")} <b style={{ color: "#e2e8f0" }}>{nodeCount}</b></span>
        <span>{t("depGraph.edges")} <b style={{ color: "#e2e8f0" }}>{edgeCount}</b></span>
        <span>
          {t("depGraph.cycles")}&nbsp;
          <b style={{ color: cycles > 0 ? "#ef4444" : "#22c55e" }}>{cycles}</b>
        </span>

        {/* Filter toggle */}
        <span style={{ marginLeft: "auto" }}>
          {[["all", t("depGraph.allImports")], ["project", t("depGraph.projectOnly")]].map(([f, label]) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                background:   filter === f ? "#2563eb" : "#141824",
                color:        filter === f ? "#fff"    : "#94a3b8",
                border:       "1px solid #1e2536",
                borderRadius: 4, padding: "3px 10px",
                cursor: "pointer", fontSize: 11, marginLeft: 6,
              }}
            >
              {label}
            </button>
          ))}
        </span>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, marginBottom: 12, fontSize: 11 }}>
        {legendItems.map(([l, c]) => (
          <span key={l} style={{ display: "flex", alignItems: "center", gap: 4, color: "#94a3b8" }}>
            <span style={{ width: 10, height: 10, background: c, borderRadius: "50%", display: "inline-block" }} />
            {l}
          </span>
        ))}
      </div>

      {/* Graph */}
      <div style={{ background: "#141824", border: "1px solid #1e2536", borderRadius: 8, padding: 8 }}>
        <ReactECharts option={option} style={{ height: 560 }} notMerge />
      </div>

      {/* Cycle list */}
      {cycles > 0 && (
        <div style={{ background: "#141824", border: "1px solid #ef4444", borderRadius: 8, padding: 16, marginTop: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#ef4444", marginBottom: 8 }}>
            {t("depGraph.circularTitle")} ({cycles})
          </div>
          {graph.cycles.map((c, i) => (
            <div key={i} style={{ fontSize: 12, color: "#fca5a5", marginBottom: 4 }}>
              {c.join(" → ")} → {c[0]}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
