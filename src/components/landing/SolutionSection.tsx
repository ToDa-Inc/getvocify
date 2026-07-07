import { Mic, Check, Rocket, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { type ComponentType } from "react";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";

interface Step {
  number: number;
  title: string;
  icon: ComponentType<{ className?: string }>;
  description: string;
  example?: string;
  data?: { label: string; value: string }[];
  confirm?: string[];
}

const StepCardBody = ({ step }: { step: Step }) => (
  <>
    <div className="flex justify-between items-start mb-6">
      <div className="w-14 h-14 rounded-2xl bg-beige text-cream flex items-center justify-center shadow-medium">
        <step.icon className="w-7 h-7" />
      </div>
      <span className="text-5xl text-beige/10 font-bold leading-none">{step.number}</span>
    </div>

    <h3 className="font-mono text-sm font-medium tracking-[0.2em] uppercase text-beige mb-3">{step.title}</h3>

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

      {step.confirm && (
        <div className="bg-success/5 rounded-2xl p-4 border border-success/20 space-y-2">
          {step.confirm.map((label) => (
            <div key={label} className="flex items-center gap-2 text-sm font-medium text-foreground">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-success/15 text-success">
                <Check className="h-2.5 w-2.5" strokeWidth={3} />
              </span>
              {label}
            </div>
          ))}
        </div>
      )}
    </div>
  </>
);

const SolutionSection = () => {
  const { t } = useLanguage();

  const steps: Step[] = [
    {
      number: 1,
      title: t.solution.s1.title,
      icon: Mic,
      description: t.solution.s1.desc,
      example: t.solution.example1,
    },
    {
      number: 2,
      title: t.solution.s2.title,
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
      icon: Rocket,
      description: t.solution.s3.desc,
      confirm: [t.solution.label1, t.solution.label2, t.solution.label3, t.solution.label4].map(
        (label) => `${label} synced`
      ),
    },
  ];

  return (
    <section id="how-it-works" className="scroll-mt-24 py-32 bg-background relative">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-20">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <span className="section-label mb-6">02 — {t.solution.label}</span>
            <h2 className="text-3xl md:text-5xl font-semibold text-foreground mb-6 tracking-tighter text-balance">
              {t.solution.title1} <span className="text-beige font-serif italic font-medium">{t.solution.title2}</span> {t.solution.title3}
            </h2>
          </motion.div>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t.solution.subtitle}
          </p>
        </div>

        <div className="grid gap-6 max-w-xl mx-auto md:max-w-6xl md:grid-cols-3 md:items-stretch">
          {steps.map((step, index) => (
            <motion.div key={step.number} {...blurReveal(index * 0.1, 24, 0.95)}>
              <div className="glass-card-strong rounded-[28px] p-8 flex flex-col h-full">
                <StepCardBody step={step} />
              </div>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center mt-8"
        >
          <div className="btn-glow inline-flex items-center gap-2 px-6 py-3 rounded-full bg-beige text-cream font-semibold text-sm">
            <Check className="w-4 h-4" />
            {t.solution.badge}
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default SolutionSection;
