import React from "react";

/**
 * Error boundary — catches render/lifecycle errors in its subtree so a single
 * crashing component (e.g. an ECharts render on malformed data) shows a
 * recoverable fallback instead of unmounting the whole React tree to a blank
 * white screen.
 *
 * Error boundaries must be class components (no hook equivalent exists), so
 * translated labels are passed in via the optional `labels` prop. Hardcoded
 * English defaults are used as a fallback so the boundary still renders even
 * when the i18n context itself is what failed.
 *
 * Props:
 *   labels?    – { title, message, detailLabel, retry, reload }
 *   onReset?   – called when the user clicks "Try Again" (e.g. to reset
 *                upstream state). The boundary clears its own error state too.
 *   children   – the protected subtree.
 */
const FALLBACK = {
  title:       "Something went wrong",
  message:     "This view crashed while rendering. Try again, or reload the page.",
  detailLabel: "Error detail",
  retry:       "Try Again",
  reload:      "Reload Page",
};

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Surface the error for debugging; in production this is where a reporter
    // (Sentry, etc.) would be wired in.
    console.error("ErrorBoundary caught an error:", error, info?.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    if (typeof this.props.onReset === "function") {
      try { this.props.onReset(); } catch (_) { /* ignore */ }
    }
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const L = { ...FALLBACK, ...(this.props.labels || {}) };
    const detail =
      this.state.error?.message || String(this.state.error || "Unknown error");

    return (
      <div style={S.wrap}>
        <div style={S.card}>
          <div style={S.title}>⚠ {L.title}</div>
          <div style={S.msg}>{L.message}</div>
          <details style={S.details}>
            <summary style={S.summary}>{L.detailLabel}</summary>
            <pre style={S.pre}>{detail}</pre>
          </details>
          <div style={S.row}>
            <button style={S.btnPrimary} onClick={this.handleRetry}>
              {L.retry}
            </button>
            <button
              style={S.btnGhost}
              onClick={() => window.location.reload()}
            >
              {L.reload}
            </button>
          </div>
        </div>
      </div>
    );
  }
}

const S = {
  wrap: {
    display: "flex", alignItems: "center", justifyContent: "center",
    minHeight: 240, height: "100%", padding: 24,
  },
  card: {
    background: "#141824", border: "1px solid #1e2536", borderRadius: 12,
    padding: 32, maxWidth: 560, width: "100%",
  },
  title: { fontSize: 18, fontWeight: 700, color: "#ef4444", marginBottom: 12 },
  msg:   { fontSize: 13, color: "#94a3b8", lineHeight: 1.6, marginBottom: 16 },
  details: { marginBottom: 20 },
  summary: { fontSize: 12, color: "#64748b", cursor: "pointer", userSelect: "none" },
  pre: {
    marginTop: 10, background: "#0f1117", border: "1px solid #2d3748",
    borderRadius: 6, padding: 12, fontSize: 12, color: "#f87171",
    whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 200, overflow: "auto",
  },
  row: { display: "flex", gap: 10 },
  btnPrimary: {
    background: "#2563eb", color: "#fff", border: "none", borderRadius: 6,
    padding: "9px 18px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  },
  btnGhost: {
    background: "transparent", color: "#94a3b8", border: "1px solid #2d3748",
    borderRadius: 6, padding: "9px 18px", fontSize: 13, cursor: "pointer",
  },
};
