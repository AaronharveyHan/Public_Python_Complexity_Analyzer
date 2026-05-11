import React from "react";

const grades = { A: "#22c55e", B: "#84cc16", C: "#eab308", D: "#f97316", F: "#ef4444" };

const s = {
  card: {
    background: "#141824",
    border: "1px solid #1e2536",
    borderRadius: 8,
    padding: "16px 20px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  label: { fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 1 },
  value: { fontSize: 28, fontWeight: 700, color: "#e2e8f0" },
  sub:   { fontSize: 12, color: "#64748b" },
};

export default function MetricCard({ label, value, sub, grade, color }) {
  const valueColor = grade ? (grades[grade] || "#e2e8f0") : (color || "#e2e8f0");
  return (
    <div style={s.card}>
      <span style={s.label}>{label}</span>
      <span style={{ ...s.value, color: valueColor }}>{value ?? "–"}</span>
      {sub && <span style={s.sub}>{sub}</span>}
    </div>
  );
}
