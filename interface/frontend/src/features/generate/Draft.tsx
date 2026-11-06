import {
  createContext,
  useContext,
  useEffect,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type {
  Category,
  ImageRole,
  OptionValue,
  UploadRecord,
} from "../../api/types";
import { useLocation } from "react-router-dom";
export interface Draft {
  category: Category;
  modelId: string;
  prompt: string;
  options: Record<string, OptionValue>;
  uploads: { record: UploadRecord; role: ImageRole }[];
  profileId: string;
  acceleratorId: string | null;
  jobId: string | null;
}
const initial: Draft = {
  category: "character",
  modelId: "mock-i3d-multiview",
  prompt: "",
  options: {},
  uploads: [],
  profileId: "default",
  acceleratorId: null,
  jobId: null,
};
const Context = createContext<{
  draft: Draft;
  setDraft: Dispatch<SetStateAction<Draft>>;
} | null>(null);
export function DraftProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [draft, setDraft] = useState(() => ({
    ...initial,
    modelId: location.pathname.includes("text-to-2d")
      ? "mock-t2d-basic"
      : location.pathname.includes("text-to-3d")
        ? "mock-t3d-basic"
        : initial.modelId,
  }));
  useEffect(() => {
    const unload = (e: BeforeUnloadEvent) => {
      if (
        draft.prompt ||
        draft.uploads.length ||
        Object.keys(draft.options).length
      ) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", unload);
    return () => window.removeEventListener("beforeunload", unload);
  }, [draft]);
  return (
    <Context.Provider value={{ draft, setDraft }}>{children}</Context.Provider>
  );
}
export function useDraft() {
  const value = useContext(Context);
  if (!value) throw new Error("DraftProvider is required.");
  return value;
}
