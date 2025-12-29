import { Zap, Target, Shield, Globe, Smartphone, Plug, Users, Edit } from "lucide-react";

const features = [
  {
    icon: Zap,
    title: "Fast",
    description: "60-second updates. Not 10 minutes of typing.",
  },
  {
    icon: Target,
    title: "Accurate",
    description: "AI understands sales terminology. Extracts deals, contacts, next steps automatically.",
  },
  {
    icon: Shield,
    title: "Secure",
    description: "GDPR compliant. EU data storage. SOC 2 Type II in progress.",
  },
  {
    icon: Globe,
    title: "Multi-Language",
    description: "Works in English, Spanish, French, German, Italian, Portuguese.",
  },
  {
    icon: Smartphone,
    title: "Mobile-First",
    description: "Record on your phone between meetings. Syncs everywhere.",
  },
  {
    icon: Plug,
    title: "Integrates with Your CRM",
    description: "HubSpot, Salesforce, Pipedrive. More coming soon.",
  },
  {
    icon: Users,
    title: "Team Features",
    description: "Shared terminology. Team analytics. Manager visibility.",
  },
  {
    icon: Edit,
    title: "Always Editable",
    description: "Review before it updates. Edit anything. You're in control.",
  },
];

const Features = () => {
  return (
    <section id="features" className="py-24 bg-background grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Everything You Need. Nothing You Don't.
          </h2>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="card-elevated bg-card hover-lift p-6"
            >
              <div className="w-12 h-12 rounded-xl bg-beige/10 flex items-center justify-center mb-4">
                <feature.icon className="w-6 h-6 text-beige" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">
                {feature.title}
              </h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Features;
