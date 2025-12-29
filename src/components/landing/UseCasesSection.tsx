import { Car, Phone, Stethoscope, Building, Briefcase } from "lucide-react";

const useCases = [
  {
    icon: Car,
    emoji: "🚗",
    title: "Field Sales Reps",
    description: "Record between client visits. Never lose a detail. CRM updated before you reach the next meeting.",
  },
  {
    icon: Phone,
    emoji: "📞",
    title: "Inside Sales Teams",
    description: "Quick notes after discovery calls. Capture objections, budget, timeline in seconds.",
  },
  {
    icon: Stethoscope,
    emoji: "🏥",
    title: "Medical Device Sales",
    description: "Detailed meeting notes with doctor terminology. Compliance-friendly documentation.",
  },
  {
    icon: Building,
    emoji: "🏢",
    title: "B2B Account Executives",
    description: "Multi-stakeholder deals. Track all decision-makers, pain points, and next steps effortlessly.",
  },
  {
    icon: Briefcase,
    emoji: "👔",
    title: "Sales Managers",
    description: "See your team's pipeline in real-time. Coach based on actual meeting notes, not guesses.",
  },
];

const UseCasesSection = () => {
  return (
    <section className="py-24 bg-background grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Perfect For Every Sales Situation
          </h2>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {useCases.map((useCase) => (
            <div
              key={useCase.title}
              className="bg-card rounded-2xl p-6 shadow-soft border border-border hover-lift"
            >
              <span className="text-3xl mb-4 block">{useCase.emoji}</span>
              <h3 className="text-lg font-semibold text-foreground mb-2">
                {useCase.title}
              </h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {useCase.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default UseCasesSection;
