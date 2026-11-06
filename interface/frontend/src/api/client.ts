import { HttpApiClient } from "./HttpApiClient";
import { MockApiClient } from "./MockApiClient";
import type { ApiClient } from "./types";
export const isMock = import.meta.env.VITE_API_MODE !== "http";
export const api: ApiClient = isMock
  ? new MockApiClient()
  : new HttpApiClient(import.meta.env.VITE_API_BASE_URL);
