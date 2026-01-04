import { useState } from "react";
import { ArrowRight, TrendingUp, Clock, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const ROICalculator = () => {
  const { t } = useLanguage();
  const [reps, setReps] = useState(10);
  const [salary, setSalary] = useState(50000);

  const hoursPerWeek = 5;
  const weeksPerYear = 48;
  const totalHours = hoursPerWeek * reps * weeksPerYear;
  const hourlyRate = salary / (weeksPerYear * 40);
  const wastedCost = Math.round(totalHours * hourlyRate);
  const vocifyCost = 25 * reps * 12;
  const savings = wastedCost - vocifyCost;
  const roi = Math.round((savings / vocifyCost) * 100);

  return (
    <section className="py-32 bg-secondary/10 relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-5xl auto">
          <div className="text-center mb-16">
            <motion.h2 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="text-3xl md:text-5xl font-bold text-foreground mb-6 tracking-tight text-balance"
            >
              {t.roi.title1} <span className="text-beige font-serif italic font-medium">{t.roi.title2}</span>
            </motion.h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              {t.roi.subtitle}
            </p>
          </div>

          <div className="grid lg:grid-cols-5 gap-8 items-start">
            <motion.div 
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              className="lg:col-span-2 glass-morphism rounded-[3rem] p-10 border border-border/50 shadow-large bg-white/60"
            >
              <h3 className="text-sm font-bold uppercase tracking-[0.3em] text-beige mb-8">Team Details</h3>
              
              <div className="space-y-8">
                <div>
                  <div className="flex justify-between mb-4">
                    <label className="text-sm font-bold text-foreground uppercase tracking-widest">{t.roi.label1}</label>
                    <span className="text-beige font-black">{reps}</span>
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
                    <span className="text-beige font-black">€{salary.toLocaleString()}</span>
                  </div>
                  <input
                    type="range"
                    min="30000"
                    max="200000"
                    step="5000"
                    value={salary}
                    onChange={(e) => setSalary(parseInt(e.target.value))}
                    className="w-full h-1.5 bg-beige/20 rounded-lg appearance-none cursor-pointer accent-beige"
                  />
                </div>

                <div className="pt-6 border-t border-border/50">
                  <div className="flex items-center gap-3 text-muted-foreground mb-2">
                    <Clock className="w-4 h-4" />
                    <span className="text-xs font-medium">{t.roi.note1}</span>
                  </div>
                  <div className="flex items-center gap-3 text-muted-foreground">
                    <Wallet className="w-4 h-4" />
                    <span className="text-xs font-medium">{t.roi.note2}</span>
                  </div>
                </div>
              </div>
            </motion.div>

            <motion.div 
              initial={{ opacity: 0, x: 20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              className="lg:col-span-3 bg-beige rounded-[3rem] p-12 text-cream shadow-large relative overflow-hidden"
            >
              <div className="relative z-10">
                <div className="grid sm:grid-cols-2 gap-12 mb-12">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] opacity-60 mb-2">{t.roi.saved}</p>
                    <p className="text-4xl font-black tracking-tight">{totalHours.toLocaleString()}h <span className="text-lg font-serif italic font-medium opacity-80">{t.roi.perYear}</span></p>
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] opacity-60 mb-2">{t.roi.potential}</p>
                    <p className="text-4xl font-black tracking-tight flex items-center gap-2">
                      {roi.toLocaleString()}%
                      <TrendingUp className="w-8 h-8 opacity-40" />
                    </p>
                  </div>
                </div>

                <div className="bg-white/10 rounded-[2.5rem] p-10 border border-white/10 backdrop-blur-sm mb-12">
                  <p className="text-xs font-bold uppercase tracking-[0.2em] opacity-60 mb-4">{t.roi.yearly}</p>
                  <p className="text-6xl md:text-7xl font-black tracking-tighter mb-4">€{savings.toLocaleString()}</p>
                  <p className="text-sm font-serif italic font-medium opacity-80 leading-relaxed">
                    {t.roi.equivalent} <span className="underline decoration-cream/30">{(savings / salary).toFixed(1)} {t.roi.additional}</span> {t.roi.byEliminating}
                  </p>
                </div>

                <div className="text-center">
                  <Button size="xl" asChild className="group bg-cream text-beige hover:bg-white rounded-full px-12 shadow-large">
                    <Link to="/dashboard">
                      {t.roi.cta}
                      <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
                    </Link>
                  </Button>
                </div>
              </div>

              {/* Decorative background circle */}
              <div className="absolute top-0 right-0 w-80 h-80 bg-white/5 rounded-full blur-3xl -z-10" />
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ROICalculator;
