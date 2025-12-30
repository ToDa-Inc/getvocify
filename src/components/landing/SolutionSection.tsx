import { ArrowDown, Mic, Eye, Check, Rocket, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

const steps = [
  {
    number: 1,
    title: "RECORD",
    time: "30s",
    icon: Mic,
    description: "Walk to your car. Tap record. Talk naturally:",
    example: `"Just met Sarah at Acme Corp. She's interested in Enterprise. Budget is €50K. Decision by Q1. She wants demo next Tuesday. Also mentioned competitor DataCo."`,
  },
  {
    number: 2,
    title: "EXTRACT",
    time: "20s",
    icon: Sparkles,
    description: "AI extracts structured data instantly:",
    data: [
      { label: "Contact", value: "Sarah Chen" },
      { label: "Company", value: "Acme Corp" },
      { label: "Deal Value", value: "€50,000" },
      { label: "Next Step", value: "Demo Tuesday" },
    ],
  },
  {
    number: 3,
    title: "SYNC",
    time: "10s",
    icon: Rocket,
    description: "CRM updated automatically. Drive to your next meeting.",
  },
];

const SolutionSection = () => {
  return (
    <section className="py-32 bg-background relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-20">
          <motion.h2 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-3xl md:text-5xl font-bold text-foreground mb-6 tracking-tight text-balance"
          >
            From Voice to <span className="font-serif italic font-medium text-beige">CRM Data</span> in 60 Seconds.
          </motion.h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            A frictionless workflow that keeps your pipeline updated without opening your laptop.
          </p>
        </div>

        <div className="max-w-4xl mx-auto">
          <div className="grid md:grid-cols-3 gap-8">
            {steps.map((step, index) => (
              <motion.div 
                key={step.number}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: index * 0.2 }}
                className="relative"
              >
                <div className="glass-morphism rounded-[2.5rem] p-8 h-full flex flex-col group hover:border-beige/30 transition-colors">
                  <div className="flex justify-between items-start mb-6">
                    <div className="w-14 h-14 rounded-2xl bg-beige text-cream flex items-center justify-center shadow-medium group-hover:scale-110 transition-transform">
                      <step.icon className="w-7 h-7" />
                    </div>
                    <span className="text-5xl font-serif italic text-beige/10 font-bold group-hover:text-beige/20 transition-colors leading-none">
                      {step.number}
                    </span>
                  </div>
                  
                  <div className="flex items-center gap-2 mb-3">
                    <h3 className="text-sm font-bold tracking-widest uppercase text-beige">{step.title}</h3>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-secondary text-muted-foreground">{step.time}</span>
                  </div>
                  
                  <p className="text-foreground font-medium mb-6 leading-relaxed">{step.description}</p>
                  
                  <div className="mt-auto">
                    {step.example && (
                      <div className="bg-secondary/40 rounded-2xl p-4 italic text-muted-foreground text-sm border border-border/50">
                        "{step.example}"
                      </div>
                    )}
                    
                    {step.data && (
                      <div className="bg-white/50 rounded-2xl p-4 grid grid-cols-2 gap-3 text-[11px] border border-border/50 shadow-soft">
                        {step.data.map((item) => (
                          <div key={item.label}>
                            <div className="text-muted-foreground uppercase tracking-tighter font-bold mb-0.5">{item.label}</div>
                            <div className="font-bold text-foreground truncate">{item.value}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {index < steps.length - 1 && (
                  <div className="hidden md:block absolute top-1/2 -right-4 translate-x-1/2 -translate-y-1/2 z-20">
                    <div className="w-8 h-8 rounded-full bg-white shadow-soft flex items-center justify-center border border-border">
                      <ArrowDown className="w-4 h-4 text-beige rotate-[270deg]" />
                    </div>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </div>

        <motion.div 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center mt-20"
        >
          <div className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-beige text-cream font-bold text-sm shadow-medium">
            <Check className="w-4 h-4" />
            Zero manual entry required.
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default SolutionSection;
