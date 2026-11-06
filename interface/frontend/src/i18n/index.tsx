import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createI18n } from "./core";
import { readLocale, writeLocale, type Locale } from "./settings";
const Context = createContext({
  ...createI18n("en"),
  setLocale: (() => {}) as (locale: Locale) => void,
});
export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, update] = useState(readLocale);
  const value = useMemo(
    () => ({
      ...createI18n(locale),
      setLocale: (next: Locale) => {
        writeLocale(next);
        update(next);
      },
    }),
    [locale],
  );
  useLayoutEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useI18n() {
  return useContext(Context);
}
