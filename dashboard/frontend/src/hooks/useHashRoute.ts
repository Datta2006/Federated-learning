import { useCallback, useEffect, useState } from "react";

export const ROUTES = [
  "overview",
  "federated",
  "air",
  "performance",
  "communication",
] as const;

export type Route = (typeof ROUTES)[number];

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  return (ROUTES as readonly string[]).includes(hash) ? (hash as Route) : "overview";
}

export function useHashRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState<Route>(readRoute);

  useEffect(() => {
    const onHashChange = () => setRoute(readRoute());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((next: Route) => {
    window.location.hash = `/${next}`;
    setRoute(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  return [route, navigate];
}
