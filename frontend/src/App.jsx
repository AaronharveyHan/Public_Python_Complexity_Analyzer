import React, { useState, useEffect, lazy, Suspense } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import Layout from "./components/Layout";
import { api } from "./api/client";
import { useTranslation } from "./i18n";

const Dashboard      = lazy(() => import("./pages/Dashboard"));
const DependencyGraph = lazy(() => import("./pages/DependencyGraph"));
const ModuleAnalysis  = lazy(() => import("./pages/ModuleAnalysis"));
const RiskList        = lazy(() => import("./pages/RiskList"));

const PageLoader = () => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
                height: "100%", color: "#64748b", fontSize: 13 }}>
    Loading…
  </div>
);

/* ── shared styles ─────────────────────────────────────────────────────── */
const S = {
  center: {
    display: "flex", flexDirection: "column", alignItems: "center",
    justifyContent: "center", height: "100%", gap: 16,
  },
  form: {
    background: "#141824", border: "1px solid #1e2536",
    borderRadius: 12, padding: 40, width: 500, maxWidth: "100%",
  },
  title: { fontSize: 22, fontWeight: 700, color: "#60a5fa", marginBottom: 8 },
  sub:   { fontSize: 13, color: "#64748b", marginBottom: 24 },
  row:   { display: "flex", gap: 10 },
  input: {
    flex: 1, background: "#0f1117", border: "1px solid #2d3748",
    borderRadius: 6, padding: "10px 14px", color: "#e2e8f0", fontSize: 14,
    outline: "none",
  },
  btn: {
    background: "#2563eb", color: "#fff", border: "none", borderRadius: 6,
    padding: "10px 20px", fontSize: 14, fontWeight: 600, cursor: "pointer",
  },
  progress: {
    background: "#141824", border: "1px solid #1e2536",
    borderRadius: 12, padding: 40, width: 500, textAlign: "center",
  },
  bar:  { background: "#1e2536", borderRadius: 4, height: 8, margin: "16px 0" },
  fill: { background: "#2563eb", borderRadius: 4, height: 8, transition: "width .3s" },
  msg:  { fontSize: 13, color: "#64748b", marginTop: 8 },
  err:  { color: "#ef4444", fontSize: 13, marginTop: 8 },
};

/* ── extract human-readable error from axios error ─────────────────────── */
function _errMsg(ex) {
  const detail = ex?.response?.data?.detail;
  if (detail) {
    const code = ex.response.status;
    if (code === 403) return `Access denied: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`;
    if (code === 404) {
      if (detail === "Not Found") {
        return "Backend route not found — run uvicorn from the project root:\n" +
               "  uvicorn backend.api.main:app --host 127.0.0.1 --port 8000";
      }
      return `Path not found on the server: ${String(detail).replace(/^Path not found: /, "")}`;
    }
    if (code === 400) return `Bad request: ${detail}`;
    if (code === 429) return `Rate limit exceeded: ${detail}`;
    return `Server error ${code}: ${detail}`;
  }
  if (!ex?.response) {
    return "Cannot connect to the backend. Make sure uvicorn is running:\n" +
           "  uvicorn backend.api.main:app --host 127.0.0.1 --port 8000";
  }
  return ex.message;
}

/* ── extract the most useful line from a Python traceback ──────────────── */
function _lastTbLine(tb) {
  if (!tb || typeof tb !== "string") return "Analysis failed";
  const lines = tb.split("\n").map((l) => l.trim()).filter(Boolean);
  return lines[lines.length - 1] || "Analysis failed";
}

/* ── startup form ──────────────────────────────────────────────────────── */
function StartForm({ onSubmit, serverPath }) {
  const { t } = useTranslation();
  const [path,       setPath]       = useState(serverPath || "");
  const [ignoreDirs, setIgnoreDirs] = useState("");
  const [err,        setErr]        = useState("");
  const [loading,    setLoading]    = useState(false);

  React.useEffect(() => {
    if (serverPath && !path) setPath(serverPath);
  }, [serverPath]);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (!path.trim()) { setErr(t("app.pathRequired")); return; }
    setLoading(true);
    const dirs = ignoreDirs.trim()
      ? ignoreDirs.split(",").map((d) => d.trim()).filter(Boolean)
      : null;
    try { await onSubmit(path.trim(), dirs); }
    catch (ex) { setErr(_errMsg(ex)); }
    finally { setLoading(false); }
  };

  return (
    <div style={S.center}>
      <form style={S.form} onSubmit={submit}>
        <div style={S.title}>{t("app.title")}</div>
        <div style={S.sub}>{t("app.subtitle")}</div>
        <div style={S.row}>
          <input
            style={S.input}
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={t("app.pathPlaceholder")}
          />
          <button style={{ ...S.btn, opacity: loading ? .6 : 1 }} type="submit" disabled={loading}>
            {loading ? t("common.loading") : t("common.analyze")}
          </button>
        </div>
        <input
          style={{ ...S.input, marginTop: 10, fontSize: 12 }}
          value={ignoreDirs}
          onChange={(e) => setIgnoreDirs(e.target.value)}
          placeholder={t("app.ignorePlaceholder")}
        />
        {err && (
          <div style={{ ...S.err, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>⚠ {err}</div>
        )}
        <div style={{ marginTop: 12, fontSize: 11, color: "#334155", lineHeight: 1.6 }}>
          {t("app.pathHint")}
          {serverPath && (
            <span
              onClick={() => setPath(serverPath)}
              style={{ color: "#60a5fa", cursor: "pointer", marginLeft: 4 }}
            >
              {t("app.useSuggested")} {serverPath}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}

/* ── progress screen ───────────────────────────────────────────────────── */
function ProgressScreen({ taskId, onDone, onError }) {
  const { t } = useTranslation();
  const [progress, setProgress] = useState(0);
  const [message,  setMessage]  = useState("");
  const [error,    setError]    = useState("");

  useEffect(() => {
    let mounted = true;
    let ws = null;
    let fallbackTimer = null;
    let receivedTerminal = false;

    const finish = (data) => {
      if (!mounted) return;
      if (data.result) onDone(data.result);
      else setError(t("app.noData"));
    };

    const handleMsg = (data) => {
      if (!mounted || data.heartbeat) return;
      if (data.progress != null) setProgress(data.progress);
      if (data.message)          setMessage(data.message);
      if (data.status === "completed") {
        receivedTerminal = true;
        // WebSocket carries slim state only — fetch full result via REST.
        api.result(taskId).then(({ data: full }) => finish(full)).catch(() => {
          if (mounted) setError(t("app.noData"));
        });
      } else if (data.status === "failed") {
        receivedTerminal = true;
        setError(_lastTbLine(data.error));
      }
    };

    const startPolling = () => {
      if (fallbackTimer) return;
      fallbackTimer = setInterval(async () => {
        try {
          const { data } = await api.result(taskId);
          if (!mounted) return;
          setProgress(data.progress || 0);
          setMessage(data.message  || "");
          if (data.status === "completed") {
            clearInterval(fallbackTimer);
            finish(data);
          } else if (data.status === "failed") {
            clearInterval(fallbackTimer);
            setError(_lastTbLine(data.error));
          }
        } catch (ex) {
          if (mounted)
            setMessage(t("app.connectionIssue", { msg: ex.message || "network error" }));
        }
      }, 1500);
    };

    try {
      ws = new WebSocket(api.wsUrl(taskId));
      ws.onmessage = (e) => { try { handleMsg(JSON.parse(e.data)); } catch (_) {} };
      ws.onerror   = ()  => { ws = null; startPolling(); };
      ws.onclose   = ()  => { if (!receivedTerminal && mounted) startPolling(); };
    } catch (_) {
      startPolling();
    }

    return () => {
      mounted = false;
      if (ws) { try { ws.close(); } catch (_) {} }
      if (fallbackTimer) clearInterval(fallbackTimer);
    };
  }, [taskId]);

  if (error) {
    return (
      <div style={S.center}>
        <div style={S.progress}>
          <div style={{ fontSize: 16, fontWeight: 600, color: "#ef4444" }}>
            {t("app.analysisFailed")}
          </div>
          <div style={{ ...S.err, marginTop: 16, lineHeight: 1.6 }}>{error}</div>
          <button
            style={{ ...S.btn, marginTop: 20, background: "#374151" }}
            onClick={onError}
          >
            {t("common.tryAgain")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={S.center}>
      <div style={S.progress}>
        <div style={{ fontSize: 16, fontWeight: 600, color: "#60a5fa" }}>
          {t("app.analysingProject")}
        </div>
        <div style={S.bar}>
          <div style={{ ...S.fill, width: `${progress}%` }} />
        </div>
        <div style={{ fontSize: 24, fontWeight: 700, color: "#e2e8f0" }}>
          {progress}%
        </div>
        <div style={S.msg}>{message}</div>
      </div>
    </div>
  );
}

/* ── main app ──────────────────────────────────────────────────────────── */
export default function App() {
  const { t } = useTranslation();
  const [taskId,     setTaskId]     = useState(null);
  const [result,     setResult]     = useState(null);
  const [serverPath, setServerPath] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.health()
      .then(({ data }) => {
        if (data?.suggested_path) setServerPath(data.suggested_path);
      })
      .catch((err) => {
        console.warn("Health check failed (backend may not be running):", err.message);
      });
  }, []);

  const handleSubmit = async (path, ignoreDirs) => {
    const { data } = await api.analyze(path, ignoreDirs);
    setTaskId(data.task_id);
    setResult(null);
  };

  const handleDone = (res) => {
    setResult(res);
    navigate("/");
  };

  const handleError = () => {
    setTaskId(null);
    setResult(null);
  };

  if (!taskId && !result) {
    return <StartForm onSubmit={handleSubmit} serverPath={serverPath} />;
  }
  if (taskId && !result) {
    return <ProgressScreen taskId={taskId} onDone={handleDone} onError={handleError} />;
  }

  const reset = () => { setTaskId(null); setResult(null); navigate("/"); };

  return (
    <Layout projectName={result?.project_name}>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginBottom: 16 }}>
        {taskId && (
          <a
            href={api.reportUrl(taskId)}
            download
            style={{
              background: "transparent", border: "1px solid #2563eb",
              color: "#60a5fa", borderRadius: 6, padding: "6px 14px",
              fontSize: 12, cursor: "pointer", textDecoration: "none",
            }}
          >
            {t("common.exportHtml")}
          </a>
        )}
        <button
          onClick={reset}
          style={{
            background: "transparent", border: "1px solid #2d3748",
            color: "#94a3b8", borderRadius: 6, padding: "6px 14px",
            fontSize: 12, cursor: "pointer",
          }}
        >
          {t("common.newAnalysis")}
        </button>
      </div>

      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/"        element={<Dashboard      result={result} />} />
          <Route path="/deps"    element={<DependencyGraph result={result} />} />
          <Route path="/modules" element={<ModuleAnalysis  result={result} />} />
          <Route path="/risks"   element={<RiskList        result={result} />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
