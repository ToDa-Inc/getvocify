import { useState } from "react";
import { ArrowRight, TrendingUp, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const ROICalculator = () => {
  const { t } = useLanguage();
  const [reps, setReps] = useState(10);
  const [salary, setSalary] = useState(50000);

  const hoursPerWeek = 5;
  const weeksPerYear = 48;
  const workYearHours = 40 * weeksPerYear; // 1920 — one full-time year in hours
  const totalHours = hoursPerWeek * reps * weeksPerYear;
  const hourlyRate = salary / workYearHours;
  /** Yearly value of time currently lost to manual CRM admin (no subscription pricing). */
  const yearlyOpportunityValue = Math.round(totalHours * hourlyRate);
  const payrollSharePct =
    reps > 0 && salary > 0
      ? Math.min(999, Math.round((yearlyOpportunityValue / (reps * salary)) * 100))
      : 0;

  return (
    <section id="calculator" className="scroll-mt-24 py-32 bg-secondary/10 relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-5xl auto">
          <div className="text-center mb-16">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
            >
              <span className="section-label mb-6">05 — {t.roi.label}</span>
              <h2 className="text-3xl md:text-5xl font-semibold text-foreground mb-6 tracking-tighter text-balance">
                {t.roi.title1} <span className="text-beige font-serif italic font-medium">{t.roi.title2}</span>
              </h2>
            </motion.div>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">{t.roi.subtitle}</p>
          </div>

          <div className="grid lg:grid-cols-5 gap-8 items-start">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              className="lg:col-span-2 glass-card-strong rounded-[28px] p-10"
            >
              <h3 className="font-mono text-sm font-medium uppercase tracking-[0.25em] text-beige mb-8">Team Details</h3>

              <div className="space-y-8">
                <div>
                  <div className="flex justify-between mb-4">
                    <label className="text-sm font-bold text-foreground uppercase tracking-widest">{t.roi.label1}</label>
                    <span className="text-beige font-bold">{reps}</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="100"
                    value={reps}
                    onChange={(e) => setReps(parseInt(e.target.value))}
                    className="w-full h-1.5 bg-beige/20 rounded-lg appearance-none cursor-pointer accent-beige"
                  />
                </div>

                <div>
                  <div className="flex justify-between mb-4">
                    <label className="text-sm font-bold text-foreground uppercase tracking-widest">{t.roi.label2}</label>
                    <span className="text-beige font-bold">€{salary.toLocaleString()}</span>
                  </div>
                  <input
                    type="range"
                    min={20000}
                    max={200000}
                    step={2000}
                    value={salary}
                    onChange={(e) => setSalary(parseInt(e.target.value))}
                    className="w-full h-1.5 bg-beige/20 rounded-lg appearance-none cursor-pointer accent-beige"
                  />
                  <p className="text-[10px] text-muted-foreground mt-2 font-medium">€20,000 – €200,000</p>
                </div>

                <div className="pt-6 border-t border-border/50">
                  <div className="flex items-center gap-3 text-muted-foreground">
                    <Clock className="w-4 h-4 shrink-0" />
                    <span className="text-xs font-medium">{t.roi.note1}</span>
                  </div>
                </div>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: 20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              className="lg:col-span-3 bg-beige rounded-[28px] p-12 text-cream relative overflow-hidden shadow-[inset_0_1px_0_rgba(255,255,255,0.15),0_22px_60px_-30px_hsla(35,30%,15%,0.6)]"
            >
              <div className="relative z-10">
                <div className="grid sm:grid-cols-2 gap-12 mb-12">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] opacity-60 mb-2">{t.roi.saved}</p>
                    <p className="text-4xl font-bold tracking-tight">
                      {totalHours.toLocaleString()}h{" "}
                      <span className="text-lg font-serif italic font-medium opacity-80">{t.roi.perYear}</span>
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] opacity-60 mb-2">{t.roi.potential}</p>
                    <p className="text-4xl font-bold tracking-tight flex items-center gap-2">
                      {payrollSharePct}%
                      <TrendingUp className="w-8 h-8 opacity-40" />
                    </p>
                  </div>
                </div>

                <div className="glass-card-dark rounded-[24px] p-10 mb-12">
                  <p className="text-xs font-bold uppercase tracking-[0.2em] opacity-60 mb-4">{t.roi.yearly}</p>
                  <p className="text-6xl md:text-7xl font-bold tracking-tighter">
                    €{yearlyOpportunityValue.toLocaleString()}
                  </p>
                </div>

                <div className="text-center">
                  <Button size="xl" asChild className="group bg-cream text-beige hover:bg-white rounded-full px-12 shadow-large">
                    <a href={DEMO_BOOKING_URL} target="_blank" rel="noopener noreferrer">
                      {t.roi.cta}
                      <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
                    </a>
                  </Button>
                </div>
              </div>

              <div className="absolute top-0 right-0 w-80 h-80 bg-white/5 rounded-full blur-3xl -z-10" />
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ROICalculator;
