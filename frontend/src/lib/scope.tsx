import { useSearchParams } from "react-router-dom";

export type Scope = "all" | "favourites";

/** Scope lives in the URL (?scope=favourites) so views are shareable and survive reloads. */
export function useScope(): [Scope, (s: Scope) => void] {
  const [params, setParams] = useSearchParams();
  const scope: Scope = params.get("scope") === "favourites" ? "favourites" : "all";
  const set = (s: Scope) => {
    const p = new URLSearchParams(params);
    if (s === "all") p.delete("scope"); else p.set("scope", s);
    setParams(p, { replace: true });
  };
  return [scope, set];
}
