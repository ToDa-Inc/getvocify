import { ArrowDown, Mic, Eye, Check, Rocket } from "lucide-react";

const steps = [
  {
    number: 1,
    title: "RECORD",
    time: "30 seconds",
    icon: Mic,
    description: "Walk to your car. Tap record. Talk naturally:",
    example: `"Just met Sarah at Acme Corp. She's interested in Enterprise. Budget is €50K. Decision by Q1. She wants demo next Tuesday. Also mentioned competitor DataCo."`,
  },
  {
    number: 2,
    title: "REVIEW",
    time: "20 seconds",
    icon: Eye,
    description: "AI extracts the data:",
    data: [
      { label: "Contact", value: "Sarah Chen" },
      { label: "Company", value: "Acme Corp" },
      { label: "Deal Value", value: "€50,000" },
      { label: "Stage", value: "Demo Scheduled" },
      { label: "Next Step", value: "Demo next Tuesday" },
      { label: "Competitor", value: "DataCo" },
    ],
  },
  {
    number: 3,
    title: "APPROVE",
    time: "10 seconds",
    icon: Check,
    description: 'Looks good? Tap "Update CRM"',
  },
  {
    number: 4,
    title: "DONE",
    time: "",
    icon: Rocket,
    description: "CRM updated. Drive to next meeting.",
  },
];

const SolutionSection = () => {
  return (
    <section className="py-24 bg-secondary/50 grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            How Voicfy Works
          </h2>
          <p className="text-xl text-muted-foreground">
            30 seconds to speak. 60 seconds to update. Done.
          </p>
        </div>

        <div className="max-w-2xl mx-auto space-y-6">
          {steps.map((step, index) => (
            <div key={step.number}>
              <div className="bg-card rounded-2xl p-6 shadow-soft border border-border">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-beige/10 flex items-center justify-center">
                    <step.icon className="w-6 h-6 text-beige" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-sm font-bold text-beige">
                        {step.number}. {step.title}
                      </span>
                      {step.time && (
                        <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded-full">
                          {step.time}
                        </span>
                      )}
                    </div>
                    <p className="text-muted-foreground mb-3">{step.description}</p>
                    
                    {step.example && (
                      <div className="bg-secondary/70 rounded-lg p-4 italic text-foreground text-sm">
                        "{step.example}"
                      </div>
                    )}
                    
                    {step.data && (
                      <div className="bg-secondary/70 rounded-lg p-4 grid grid-cols-2 gap-2 text-sm">
                        {step.data.map((item) => (
                          <div key={item.label}>
                            <span className="text-muted-foreground">{item.label}:</span>{" "}
                            <span className="font-medium text-foreground">{item.value}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
              
              {index < steps.length - 1 && (
                <div className="flex justify-center py-2">
                  <ArrowDown className="w-5 h-5 text-muted-foreground/50" />
                </div>
              )}
            </div>
          ))}
        </div>

        <p className="text-center text-lg font-medium text-foreground mt-12">
          That's it. <span className="text-muted-foreground">No typing. No forms. No remembering.</span>
        </p>
      </div>
    </section>
  );
};

export default SolutionSection;
