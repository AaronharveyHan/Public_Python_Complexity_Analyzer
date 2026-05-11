import React from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "../i18n";

const styles = {
  root: {
    display: "flex",
    height: "100vh",
    overflow: "hidden",
  },
  sidebar: {
    width: 200,
    background: "#141824",
    borderRight: "1px solid #1e2536",
    display: "flex",
    flexDirection: "column",
    padding: "16px 0",
    flexShrink: 0,
  },
  logo: {
    padding: "0 20px 20px",
    borderBottom: "1px solid #1e2536",
    marginBottom: 8,
  },
  logoTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: "#60a5fa",
    letterSpacing: 0.5,
  },
  logoSub: {
    fontSize: 11,
    color: "#64748b",
    marginTop: 2,
  },
  navItem: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 20px",
    fontSize: 13,
    color: "#94a3b8",
    textDecoration: "none",
    borderLeft: "3px solid transparent",
    transition: "all .15s",
  },
  navActive: {
    color: "#60a5fa",
    background: "rgba(96,165,250,.08)",
    borderLeft: "3px solid #60a5fa",
  },
  langSwitcher: {
    marginTop: "auto",
    borderTop: "1px solid #1e2536",
    padding: "12px 20px",
    display: "flex",
    gap: 6,
  },
  main: {
    flex: 1,
    overflow: "auto",
    padding: 24,
    background: "#0f1117",
  },
};

export default function Layout({ children, projectName }) {
  const { t, lang, setLang } = useTranslation();

  const NAV = [
    { to: "/",        label: t("layout.dashboard"),  icon: "⬛" },
    { to: "/deps",    label: t("layout.dependency"), icon: "🕸" },
    { to: "/modules", label: t("layout.modules"),    icon: "📦" },
    { to: "/risks",   label: t("layout.riskList"),   icon: "⚠️" },
  ];

  return (
    <div style={styles.root}>
      <aside style={styles.sidebar}>
        <div style={styles.logo}>
          <div style={styles.logoTitle}>{t("layout.brand")}</div>
          <div style={styles.logoSub}>{projectName || t("layout.analyzer")}</div>
        </div>

        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            style={({ isActive }) =>
              isActive ? { ...styles.navItem, ...styles.navActive } : styles.navItem
            }
          >
            <span>{n.icon}</span>
            <span>{n.label}</span>
          </NavLink>
        ))}

        {/* Language toggle */}
        <div style={styles.langSwitcher}>
          {[["en", "EN"], ["zh", "中"]].map(([code, label]) => (
            <button
              key={code}
              onClick={() => setLang(code)}
              style={{
                flex: 1,
                background:   lang === code ? "#2563eb" : "transparent",
                color:        lang === code ? "#fff"    : "#64748b",
                border:       "1px solid #1e2536",
                borderRadius: 4,
                fontSize:     12,
                fontWeight:   lang === code ? 700 : 400,
                cursor:       "pointer",
                padding:      "5px 0",
                transition:   "all .15s",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </aside>

      <main style={styles.main}>{children}</main>
    </div>
  );
}
