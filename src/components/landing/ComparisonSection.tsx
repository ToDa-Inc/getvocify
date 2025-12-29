import { Check, X, Minus } from "lucide-react";

const comparisonData = [
  {
    feature: "Speed",
    voicfy: "60 seconds",
    traditional: "10+ minutes",
    voiceMemos: "5 min (but you still type)",
    otherTools: "2-5 minutes",
  },
  {
    feature: "Accuracy",
    voicfy: "AI-extracted",
    traditional: "Manual (errors)",
    voiceMemos: "You transcribe",
    otherTools: "Varies",
  },
  {
    feature: "Cost",
    voicfy: "€25/month",
    traditional: "Time = €1,200/year",
    voiceMemos: '"Free" = €1,200/year',
    otherTools: "€75-150/month",
  },
  {
    feature: "Mobile",
    voicfy: true,
    traditional: false,
    voiceMemos: true,
    otherTools: false,
  },
  {
    feature: "Multi-CRM",
    voicfy: true,
    traditional: "One CRM",
    voiceMemos: false,
    otherTools: false,
  },
  {
    feature: "European",
    voicfy: true,
    traditional: false,
    voiceMemos: null,
    otherTools: false,
  },
];

const renderCell = (value: boolean | string | null) => {
  if (value === true) {
    return <Check className="w-5 h-5 text-green-600 mx-auto" />;
  }
  if (value === false) {
    return <X className="w-5 h-5 text-destructive mx-auto" />;
  }
  if (value === null) {
    return <Minus className="w-5 h-5 text-muted-foreground mx-auto" />;
  }
  return <span className="text-sm">{value}</span>;
};

const ComparisonSection = () => {
  return (
    <section className="py-24 bg-secondary/50 grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Why Voicfy vs. Everything Else?
          </h2>
        </div>

        <div className="max-w-5xl mx-auto overflow-x-auto">
          <table className="w-full min-w-[600px]">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-4 px-4 text-sm font-medium text-muted-foreground"></th>
                <th className="py-4 px-4 text-center">
                  <span className="inline-block px-4 py-2 bg-beige text-cream rounded-lg font-semibold text-sm">
                    Voicfy
                  </span>
                </th>
                <th className="py-4 px-4 text-sm font-medium text-muted-foreground text-center">
                  Traditional CRM
                </th>
                <th className="py-4 px-4 text-sm font-medium text-muted-foreground text-center">
                  Voice Memos
                </th>
                <th className="py-4 px-4 text-sm font-medium text-muted-foreground text-center">
                  Other Tools
                </th>
              </tr>
            </thead>
            <tbody>
              {comparisonData.map((row, index) => (
                <tr key={row.feature} className={index % 2 === 0 ? "bg-card/50" : ""}>
                  <td className="py-4 px-4 font-medium text-foreground text-sm">
                    {row.feature}
                  </td>
                  <td className="py-4 px-4 text-center font-medium text-green-600">
                    {renderCell(row.voicfy)}
                  </td>
                  <td className="py-4 px-4 text-center text-muted-foreground">
                    {renderCell(row.traditional)}
                  </td>
                  <td className="py-4 px-4 text-center text-muted-foreground">
                    {renderCell(row.voiceMemos)}
                  </td>
                  <td className="py-4 px-4 text-center text-muted-foreground">
                    {renderCell(row.otherTools)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};

export default ComparisonSection;
