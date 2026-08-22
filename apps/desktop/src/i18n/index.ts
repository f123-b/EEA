import { useCallback, useEffect, useState } from "react";

import enUS from "./en-US.json";
import zhCN from "./zh-CN.json";

export type Locale = "zh-CN" | "en-US";
export const DEFAULT_LOCALE: Locale = "zh-CN";
export const LOCALE_STORAGE_KEY = "eea.locale";

const LOCALE_EVENT = "eea-locale-changed";
const catalogs: Record<Locale, Record<string, string>> = { "zh-CN": zhCN, "en-US": enUS };

function readLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const value = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  return value === "en-US" || value === "zh-CN" ? value : DEFAULT_LOCALE;
}

export function useI18n() {
  const [locale, setLocaleState] = useState<Locale>(readLocale);

  useEffect(() => {
    const handleLocaleChange = () => setLocaleState(readLocale());
    window.addEventListener(LOCALE_EVENT, handleLocaleChange);
    return () => window.removeEventListener(LOCALE_EVENT, handleLocaleChange);
  }, []);

  const setLocale = useCallback((nextLocale: Locale) => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, nextLocale);
    setLocaleState(nextLocale);
    window.dispatchEvent(new Event(LOCALE_EVENT));
  }, []);

  const text = useCallback((value: string): string => {
    return catalogs[locale][value] ?? catalogs["en-US"][value] ?? value;
  }, [locale]);

  return { locale, setLocale, text };
}
