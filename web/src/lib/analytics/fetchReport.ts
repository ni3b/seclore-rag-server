export async function fetchReport(start: string, end: string) {
  const response = await fetch(
    `/api/analytics/report?start=${start}&end=${end}`,
    { method: "GET" }
  );

  if (!response.ok) {
    throw new Error("Failed to download report");
  }

  const blob = await response.blob();

  // Extract filename safely from Content-Disposition
  const disposition = response.headers.get("Content-Disposition");
  let filename = "report.xlsx";
  if (disposition) {
    const match = disposition.match(/filename="([^"]+)"/);
    if (match?.[1]) {
      filename = match[1];
    }
  }

  return { blob, filename };
}
