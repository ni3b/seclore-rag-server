// src/app/dashboard/page.tsx
"use client";

import { useState } from "react";
import { useAnalytics } from "@/hooks/useAnalytics";
import { fetchReport } from "@/lib/analytics/fetchReport";
import SummaryCards from "@/components/analytics/SummaryCards";
import { UsageTrends } from "@/components/analytics/UsageTrends";
import { AssistantDonutChart } from "@/components/analytics/AssistantDonutChart";
import { AdminPageTitle } from "@/components/admin/Title";
import { BarChartIcon } from "@/components/icons/icons";
import { LikesDislikes } from "@/components/analytics/LikesDislikes";
import { Spinner } from "@/components/Spinner";

function getDefaultDates() {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 30);
  return {
    start: start.toISOString().slice(0, 10), // YYYY-MM-DD
    end: end.toISOString().slice(0, 10),
  };
}

function getToday(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}


export default function Page() {
  const [pendingRange, setPendingRange] = useState(getDefaultDates());
  const [appliedRange, setAppliedRange] = useState(getDefaultDates());
  const [downloading, setDownloading] = useState(false);

  const { data, loading, error } = useAnalytics(
    appliedRange.start,
    appliedRange.end
  );

  const handleApply = () => {
    setAppliedRange(pendingRange);
  };

  const handleDownloadReport = async () => {
    try {
      setDownloading(true);
      const { blob, filename } = await fetchReport(
        appliedRange.start,
        appliedRange.end
      );

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed", err);
      alert("Could not download report");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="p-6">
      <AdminPageTitle
        icon={<BarChartIcon className="w-7 h-7" />}
        title="Analytics Dashboard"
        farRightElement={
          <button
            onClick={handleDownloadReport}
            disabled={downloading}
            className={`px-3 py-1 rounded text-white ${
              downloading ? "bg-gray-400 cursor-not-allowed" : "bg-green-600"
            }`}
          >
            {downloading ? (
            <>
              <Spinner />
              Downloading...
            </>
          ) : (
            "Download Report"
          )}
          </button>
        }
      />

      {/* Date Range Controls + Likes/Dislikes */}
      <div className="flex items-center justify-between mb-4">
        {/* Left side: date pickers + apply */}
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={pendingRange.start}
            max={getToday()}   // prevents selecting future dates
            onChange={(e) =>
              setPendingRange((prev) => ({ ...prev, start: e.target.value }))
            }
            className="border rounded p-1"
          />
          <input
            type="date"
            value={pendingRange.end}
            max={getToday()}   // prevents selecting future dates
            onChange={(e) =>
              setPendingRange((prev) => ({ ...prev, end: e.target.value }))
            }
            className="border rounded p-1"
          />

          <button
            onClick={handleApply}
            className="px-3 py-1 bg-blue-600 text-white rounded"
          >
            Apply
          </button>
        </div>

        {/* Right side: likes/dislikes */}
        {data && (
          <LikesDislikes
            likes={data.totals.likes}
            dislikes={data.totals.dislikes}
          />
        )}
      </div>

      {/* Analytics State */}
      {loading && <p>Loading...</p>}
      {error && <p className="text-red-500">{error}</p>}
      {data && (
        <>
          <SummaryCards totals={data.totals} />
          <div className="mt-6">
              <UsageTrends bucketed={data.bucketed} />
          </div>
          <div className="mt-6">
              <AssistantDonutChart data={data.assistant_data} />
          </div>
        </>
      )}
    </div>
  );
}
