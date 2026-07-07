import { Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";

const ComparisonSection = () => {
  const { t } = useLanguage();

  const rows = [
    { feature: t.comparison.f1, without: t.comparison.t1, withCopilot: t.comparison.v1 },
    { feature: t.comparison.f2, without: t.comparison.t2, withCopilot: t.comparison.v2 },
    { feature: t.comparison.f3, without: t.comparison.t3, withCopilot: t.comparison.v3 },
    { feature: t.comparison.f4, without: t.comparison.t4, withCopilot: t.comparison.v4 },
    { feature: t.comparison.f5, without: t.comparison.t5, withCopilot: t.comparison.v5 },
  ];

  return (
    <section className="py-32 bg-white relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-20">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <span className="section-label mb-6">06 — {t.comparison.label}</span>
            <h2 className="text-3xl md:text-5xl font-semibold text-foreground mb-6 tracking-tighter">
              {t.comparison.title1} <span className="text-beige font-serif italic font-medium">{t.comparison.title2}</span>
            </h2>
          </motion.div>
        </div>

        <motion.div {...blurReveal(0, 32, 0.95)} className="max-w-4xl mx-auto">
          <div className="glass-card-strong rounded-[28px] overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="py-8 px-6 text-left font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground/60 bg-secondary/10" />
                  <th className="py-8 px-6 text-center font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground/60">
                    {t.comparison.without}
                  </th>
                  <th className="py-8 px-6 text-center bg-beige text-cream">
                    <div className="flex items-center justify-center gap-2">
                      <Sparkles className="w-4 h-4" />
                      <span className="text-sm font-bold uppercase tracking-widest">{t.comparison.with}</span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.feature} className="border-b border-border/50 last:border-0 hover:bg-beige/5 transition-colors">
                    <td className="py-6 px-6 font-bold text-foreground text-sm tracking-tight">{row.feature}</td>
                    <td className="py-6 px-6 text-center text-muted-foreground text-sm">{row.without}</td>
                    <td className="py-6 px-6 text-center bg-beige/95 shadow-inner text-cream text-sm font-bold">
                      {row.withCopilot}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default ComparisonSection;
