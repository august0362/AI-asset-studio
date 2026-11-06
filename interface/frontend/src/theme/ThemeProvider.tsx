import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";
import {
  defaults,
  readTheme,
  resolveTheme,
  writeTheme,
  type ThemeSettings,
} from "./settings";
const darkQuery = "(prefers-color-scheme: dark)";
function media() {
  return window.matchMedia?.(darkQuery);
}
const Context = createContext({
  settings: defaults,
  theme: resolveTheme(defaults, false),
  setSettings: (() => {}) as (settings: ThemeSettings) => void,
});
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [settings, update] = useState(readTheme);
  const [dark, setDark] = useState(() => media()?.matches ?? false);
  const theme = resolveTheme(settings, dark);
  useEffect(() => {
    const query = media();
    if (!query) return;
    const changed = () => setDark(query.matches);
    changed();
    query.addEventListener("change", changed);
    return () => query.removeEventListener("change", changed);
  }, []);
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return (
    <Context.Provider
      value={{
        settings,
        theme,
        setSettings: (next) => update(writeTheme(next)),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useTheme() {
  return useContext(Context);
}
