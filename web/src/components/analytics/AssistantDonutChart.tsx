// src/components/analytics/AssistantDonutChart.tsx
"use client";

import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

type AssistantRow = [number, string, number, number, number, number];
// [id, name, messages, users, dislikes, tokens]

type Props = { data: AssistantRow[] };

const COLORS = ["#2563eb", "#f97316", "#16a34a", "#9333ea", "#e11d48"];

function MetricDonut({
  data,
  metric,
}: {
  data: AssistantRow[];
  metric: "messages" | "users" | "tokens";
}) {
  const chartData = data.map(([id, name, messages, users, dislikes, tokens]) => ({
    name,
    value:
      metric === "messages"
        ? messages
        : metric === "users"
        ? users
        : tokens,
  }));

  const total = chartData.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="p-4 border rounded-xl shadow-sm flex flex-col items-center relative">
      <h3 className="font-medium capitalize mb-2">{metric}</h3>
      <div className="relative w-full h-64">
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={chartData}
              dataKey="value"
              innerRadius={70}
              outerRadius={90}
              paddingAngle={3}
            >
              {chartData.map((_, idx) => (
                <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>

        {/* Centered Total */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-lg font-bold">{total.toLocaleString()}</span>
          <span className="text-xs text-gray-500">Total</span>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-2 justify-center mt-2">
        {chartData.map((d, idx) => (
          <div key={d.name} className="flex items-center text-xs">
            <span
              className="w-3 h-3 mr-1 rounded-sm"
              style={{ backgroundColor: COLORS[idx % COLORS.length] }}
            />
            {d.name}: {d.value.toLocaleString()}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AssistantDonutChart({ data }: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <MetricDonut data={data} metric="messages" />
      <MetricDonut data={data} metric="users" />
      <MetricDonut data={data} metric="tokens" />
    </div>
  );
}
