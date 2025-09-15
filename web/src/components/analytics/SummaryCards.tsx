import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SummaryCards({ totals }: { totals: any }) {
  const items = [
    { label: "Active Users", value: totals.active_users },
    { label: "Queries", value: totals.queries },
    { label: "Input Tokens", value: totals.input_tokens },
    { label: "Output Tokens", value: totals.output_tokens },
  ];
  
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {items.map((i) => (
        <Card key={i.label}>
          <CardHeader>
            <CardTitle>{i.label}</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold">{i.value}</CardContent>
        </Card>
      ))}
    </div>
  );
}
