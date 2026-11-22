import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type User } from "./api";

export function useAuth() {
  const q = useQuery({ queryKey: ["me"], queryFn: () => api<{ user: User | null }>("/api/auth/me"), staleTime: 60_000 });
  return { user: q.data?.user ?? null, loading: q.isLoading };
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/api/auth/logout", { method: "POST" }),
    onSuccess: () => { qc.clear(); },
  });
}

export function useFavourite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, on }: { slug: string; on: boolean }) =>
      api(`/api/favourites/${encodeURIComponent(slug)}`, { method: on ? "PUT" : "DELETE" }),
    onSuccess: () => {
      for (const k of ["groups", "group", "graph", "stats", "activity", "favourites", "conflict"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });
}
