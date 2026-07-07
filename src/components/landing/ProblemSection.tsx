import { Check, X } from "lucide-react";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const ProblemSection = () => {
  const { t } = useLanguage();

  return (
    <section className="py-32 bg-secondary/20 relative overflow-hidden border-t border-border/50">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-4xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="text-center mb-16"
          >
            <span className="section-label mb-6">01 — {t.problem.label}</span>
            <h2 className="text-4xl md:text-6xl font-semibold text-foreground mb-0 tracking-tighter leading-[1.05] text-balance">
              {t.problem.title1}
              <br />
              <span className="text-beige font-serif italic font-medium">{t.problem.title2}</span>
            </h2>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6 }}
              className="glass-card rounded-[28px] p-8"
            >
              <h3 className="font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground mb-6">
                {t.problem.likeTitle}
              </h3>
              <ul className="space-y-4">
                {t.problem.likeItems.map((item: string) => (
                  <li key={item} className="flex items-center gap-3 text-lg font-medium text-foreground">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-success/15 text-success">
                      <Check className="h-3.5 w-3.5" strokeWidth={3} />
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="glass-card-strong rounded-[28px] p-8"
            >
              <h3 className="font-mono text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground mb-6">
                {t.problem.hateTitle}
              </h3>
              <ul className="space-y-4">
                {t.problem.hateItems.map((item: string) => (
                  <li key={item} className="flex items-center gap-3 text-lg font-medium text-foreground/70">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                      <X className="h-3.5 w-3.5" strokeWidth={3} />
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ProblemSection;
