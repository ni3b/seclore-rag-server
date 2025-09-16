export type AnalyticsResponse = {
  totals: {
    active_users: number;
    queries: number;
    input_tokens: number;
    output_tokens: number;
    likes: number;
    dislikes: number;
  };
  bucketed: [string, number, number, number, number, number][];
  assistant_data: [number, string, number, number, number, number][];
};

export async function fetchAnalytics(
  start: string,
  end: string
): Promise<AnalyticsResponse> {
  const res = await fetch(`/api/analytics?start=${start}&end=${end}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch analytics");
  return res.json();
}
