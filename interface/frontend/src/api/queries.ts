import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { JobFilters, Scenario } from "./types";
import { MockApiClient } from "./MockApiClient";
export function useStudioData(profile = "default", scenario?: Scenario) {
  const catalog = useQuery({
    queryKey: ["catalog"],
    queryFn: () => api.catalog(),
  });
  const models = useQuery({
    queryKey: ["models"],
    queryFn: () => api.models(),
  });
  const profiles = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api.profiles(),
  });
  const snapshot = useQuery({
    queryKey: ["snapshot", profile, scenario],
    queryFn: () => {
      if (scenario && api instanceof MockApiClient) api.setScenario(scenario);
      return api.snapshot(profile);
    },
    refetchInterval: (q) =>
      q.state.data?.session_status === "running" ? 15_000 : 60_000,
  });
  return {
    catalog: catalog.data,
    models: models.data?.models,
    profiles: profiles.data?.profiles,
    snapshot: snapshot.data,
    error: catalog.error ?? models.error ?? profiles.error ?? snapshot.error,
  };
}
export function useJobs(filters: JobFilters = {}) {
  return useInfiniteQuery({
    queryKey: ["jobs", filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.jobs({ ...filters, cursor: pageParam }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: 2000,
  });
}
export function useJob(id: string | null) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => api.job(id!),
    enabled: !!id,
    refetchInterval: (q) =>
      q.state.data && ["completed", "failed"].includes(q.state.data.status)
        ? false
        : 2000,
  });
}
