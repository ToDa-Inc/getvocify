import { Mic, Sparkles, Rocket } from "lucide-react";

const features = [
  {
    icon: Mic,
    title: "Speak",
    description: "Record a 60-second voice memo after your meeting",
    gradient: "from-beige/10 to-transparent",
  },
  {
    icon: Sparkles,
    title: "Review",
    description: "AI extracts deals, contacts, and next steps automatically",
    gradient: "from-beige/10 to-transparent",
  },
  {
    icon: Rocket,
    title: "Done",
    description: "Approve and watch your CRM update in real-time",
    gradient: "from-beige/10 to-transparent",
  },
];

const Features = () => {
  return (
    <section id="features" className="py-24 bg-secondary/50 grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            How Vocify Works
          </h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            Three simple steps to transform your sales workflow
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {features.map((feature, index) => (
            <div
              key={feature.title}
              className="card-elevated bg-card hover-lift group"
            >
              <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${feature.gradient} bg-beige/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300`}>
                <feature.icon className="w-7 h-7 text-beige" />
              </div>
              
              <div className="flex items-center gap-3 mb-3">
                <span className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center text-sm font-semibold text-foreground">
                  {index + 1}
                </span>
                <h3 className="text-xl font-semibold text-foreground">
                  {feature.title}
                </h3>
              </div>
              
              <p className="text-muted-foreground leading-relaxed">
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
