import { useCallback, useState } from "react";

/** The Text→2D auto-run switch (FR-J6) is remembered per browser. Storage can be unavailable: default on. */
export const AUTO_RUN_KEY = "aas.generate.autoRun";

export function readAutoRun(): boolean {
  try {
    return window.localStorage.getItem(AUTO_RUN_KEY) !== "false";
  } catch {
    return true;
  }
}

export function useAutoRunPreference(): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(readAutoRun);
  const update = useCallback((next: boolean) => {
    setValue(next);
    try {
      window.localStorage.setItem(AUTO_RUN_KEY, String(next));
    } catch {
      // private window or blocked storage: the switch still works for this page
    }
  }, []);
  return [value, update];
}
