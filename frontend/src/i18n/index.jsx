import React, { createContext, useContext, useState } from "react";
import en from "./en";
import zh from "./zh";

const LANGS = { en, zh };

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(
    () => localStorage.getItem("lang") || "en"
  );

  const setLang = (l) => {
    setLangState(l);
    localStorage.setItem("lang", l);
  };

  /**
   * Translate a dot-path key, optionally substituting {var} placeholders.
   * Falls back to English, then to the key itself.
   *
   * Usage:
   *   t("app.title")
   *   t("moduleAnalysis.more", { n: 5 })  →  "+5 more" / "还有 5 个"
   */
  const _UNSAFE = new Set(["__proto__", "constructor", "prototype"]);

  const t = (key, vars) => {
    const lookup = (dict) => {
      let val = dict;
      for (const k of key.split(".")) {
        if (_UNSAFE.has(k)) return undefined;
        val = val?.[k];
      }
      return val;
    };

    let val = lookup(LANGS[lang]) ?? lookup(LANGS.en) ?? key;

    if (vars && typeof val === "string") {
      val = val.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
    }
    return val;
  };

  return (
    <I18nContext.Provider value={{ t, lang, setLang }}>
      {children}
    </I18nContext.Provider>
  );
}

export const useTranslation = () => useContext(I18nContext);
