import { useCallback, useMemo, useState } from "react";
import { LANG_KEY, makeAuthT, readLang } from "@/lib/authI18n";

// Language for the signed-out pages. Persists under the same key the app uses.
export function useAuthLang() {
  const [lang, setLang] = useState(() => readLang());
  const toggle = useCallback(() => {
    setLang((cur) => {
      const next = cur === "ar" ? "en" : "ar";
      try { localStorage.setItem(LANG_KEY, next); } catch { /* storage unavailable */ }
      return next;
    });
  }, []);
  const t = useMemo(() => makeAuthT(lang), [lang]);
  return { lang, dir: lang === "ar" ? "rtl" : "ltr", t, toggle };
}
