import { useCallback, useEffect, useState, type DependencyList } from "react";

/** Loads data when `deps` change; ignores responses that arrive after a newer
 * request (e.g. when the user switches district quickly). */
export function useLoad<T>(load: () => Promise<T>, deps: DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableLoad = useCallback(load, deps);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);
    stableLoad()
      .then((result) => current && setData(result))
      .catch((err: unknown) => current && setError(err))
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [stableLoad, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, loading, reload };
}
