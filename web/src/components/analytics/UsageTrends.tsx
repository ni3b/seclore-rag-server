"use client";

import { useState, useMemo } from "react";
import {
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

type BucketedRow = [string, number, number, number, number, number]; 
// [timestamp, active_users, queries, input_tokens, output_tokens, dislikes]

type Props = {
  bucketed: BucketedRow[];
};

type ViewMode = "day" | "week" | "month";

export function UsageTrends({ bucketed }: Props) {
  const [view, setView] = useState<ViewMode>("day");

  // utility to get start of week
  function getWeekKey(date: Date) {
    const d = new Date(date);
    const day = d.getUTCDay(); // 0=Sunday
    const diff = d.getUTCDate() - day + (day === 0 ? -6 : 1); // Monday as start
    const weekStart = new Date(d.setUTCDate(diff));
    return weekStart.toISOString().slice(0, 10);
  }

  // utility to get YYYY-MM
  function getMonthKey(date: Date) {
    return date.toISOString().slice(0, 7);
  }

  // aggregate based on view mode
  const chartData = useMemo(() => {
    if (!bucketed) return [];

    const map = new Map<
      string,
      { 
        active_users: number; 
        queries: number; 
        input_tokens: number; 
        output_tokens: number;
        dislikes: number; 
        count: number;
      }
    >();

    for (const [ts, active_users, queries, input_tokens, output_tokens, dislikes] of bucketed) {
      const date = new Date(ts);
      let key: string;

      if (view === "day") {
        key = ts.slice(0, 10); // YYYY-MM-DD
      } else if (view === "week") {
        key = getWeekKey(date);
      } else {
        key = getMonthKey(date);
      }

      if (!map.has(key)) {
        map.set(key, {
          active_users: 0,
          queries: 0,
          input_tokens: 0,
          output_tokens: 0,
          dislikes: 0,
          count: 0,
        });
      }

      const agg = map.get(key)!;
      agg.active_users += active_users;
      agg.queries += queries;
      agg.input_tokens += input_tokens;
      agg.output_tokens += output_tokens;
      agg.dislikes += dislikes;
      agg.count += 1;
    }

    // for weekly/monthly, we might want averages of active_users but sums of tokens/queries
    return Array.from(map.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([key, agg]) => ({
        date: key,
        active_users: view === "day" ? agg.active_users : Math.round(agg.active_users / agg.count),
        queries: agg.queries,
        input_tokens: agg.input_tokens,
        output_tokens: agg.output_tokens,
        dislikes: agg.dislikes,
      }));
  }, [bucketed, view]);

  return (
    <div className="p-4 bg-white rounded shadow">
      <div className="flex justify-between items-center mb-4">
        <h2 className="font-semibold">Usage Trends</h2>
        <div className="space-x-2">
          {(["day", "week", "month"] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setView(mode)}
              className={`px-3 py-1 rounded ${
                view === mode ? "bg-blue-600 text-white" : "bg-gray-200"
              }`}
            >
              {mode[0].toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="active_users" stroke="#dc2626" strokeWidth={2} />
          <Line type="monotone" dataKey="queries" stroke="#2563eb" strokeWidth={2} />
          <Line type="monotone" dataKey="input_tokens" stroke="#16a34a" strokeWidth={2} />
          <Line type="monotone" dataKey="output_tokens" stroke="#f59e0b" strokeWidth={2} />
          <Line type="monotone" dataKey="dislikes" stroke="#d93aa9ff" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
