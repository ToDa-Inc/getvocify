import { ArrowDown, Mic, Eye, Check, Rocket, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const SolutionSection = () => {
  const { t } = useLanguage();

  const steps = [
    {
      number: 1,
      title: t.solution.s1.title,
      time: t.solution.s1.time,
      icon: Mic,
      description: t.solution.s1.desc,
      example: t.solution.example1,
    },
    {
      number: 2,
      title: t.solution.s2.title,
      time: t.solution.s2.time,
      icon: Sparkles,
      description: t.solution.s2.desc,
      data: [
        { label: t.solution.label1, value: "Sarah Chen" },
        { label: t.solution.label2, value: "Acme Corp" },
        { label: t.solution.label3, value: "€50,000" },
        { label: t.solution.label4, value: "Demo Tuesday" },
      ],
    },
    {
      number: 3,
      title: t.solution.s3.title,
      time: t.solution.s3.time,
      icon: Rocket,
      description: t.solution.s3.desc,
    },
  ];

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
            {t.solution.title1} <span className="text-beige font-black">{t.solution.title2}</span> {t.solution.title3}
          </motion.h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t.solution.subtitle}
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
                    <span className="text-5xl text-beige/10 font-black group-hover:text-beige/20 transition-colors leading-none">
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
                      <div className="bg-secondary/40 rounded-2xl p-4 text-muted-foreground text-sm border border-border/50">
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
            {t.solution.badge}
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default SolutionSection;
