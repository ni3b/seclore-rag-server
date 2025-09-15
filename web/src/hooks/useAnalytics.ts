import { useEffect, useState } from "react";
import { fetchAnalytics, AnalyticsResponse } from "@/lib/analytics/fetchAnalytics";

export function useAnalytics(start: string, end: string) {
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true; // prevent state updates on unmounted components

    async function loadAnalytics() {
      setLoading(true);
      setError(null);

      try {
        const result = await fetchAnalytics(start, end);
        if (isMounted) setData(result);
      } catch (err) {
        if (isMounted) setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadAnalytics();

    return () => {
      isMounted = false;
    };
  }, [start, end]);

  return { data, loading, error };
}
