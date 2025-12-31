import { Check, X, Minus, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const ComparisonSection = () => {
  const { t } = useLanguage();

  const comparisonData = [
    {
      feature: t.comparison.f1,
      vocify: t.comparison.v1,
      traditional: t.comparison.t1,
      voiceMemos: t.comparison.m1,
    },
    {
      feature: t.comparison.f2,
      vocify: t.comparison.v2,
      traditional: t.comparison.t2,
      voiceMemos: t.comparison.m2,
    },
    {
      feature: t.comparison.f3,
      vocify: t.comparison.v3,
      traditional: t.comparison.t3,
      voiceMemos: t.comparison.m3,
    },
    {
      feature: t.comparison.f4,
      vocify: true,
      traditional: true,
      voiceMemos: false,
    },
    {
      feature: t.comparison.f5,
      vocify: true,
      traditional: false,
      voiceMemos: true,
    },
    {
      feature: t.comparison.f6,
      vocify: true,
      traditional: false,
      voiceMemos: false,
    },
  ];

  const renderCell = (value: boolean | string | null, isVocify: boolean) => {
    if (value === true) {
      return <Check className={`w-5 h-5 mx-auto ${isVocify ? "text-cream" : "text-green-600"}`} />;
    }
    if (value === false) {
      return <X className="w-5 h-5 text-destructive mx-auto" />;
    }
    if (value === null) {
      return <Minus className="w-5 h-5 text-muted-foreground mx-auto" />;
    }
    return <span className={`text-sm font-bold ${isVocify ? "text-cream" : "text-foreground"}`}>{value}</span>;
  };

  return (
    <section className="py-32 bg-white relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-20">
          <motion.h2 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-3xl md:text-5xl font-bold text-foreground mb-6 tracking-tight"
          >
            {t.comparison.title1} <span className="text-beige font-black">{t.comparison.title2}</span>
          </motion.h2>
        </div>

        <div className="max-w-4xl mx-auto">
          <div className="glass-morphism rounded-[3rem] overflow-hidden shadow-large border border-border/50">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="py-8 px-6 text-left text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground/60 bg-secondary/10">{t.comparison.method}</th>
                  <th className="py-8 px-6 text-center bg-beige text-cream">
                    <div className="flex items-center justify-center gap-2 mb-1">
                      <Sparkles className="w-4 h-4" />
                      <span className="text-sm font-black uppercase tracking-widest">{t.comparison.vocify}</span>
                    </div>
                  </th>
                  <th className="py-8 px-6 text-center text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground/60 hidden sm:table-cell">{t.comparison.traditional}</th>
                  <th className="py-8 px-6 text-center text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground/60 hidden md:table-cell">{t.comparison.voiceMemos}</th>
                </tr>
              </thead>
              <tbody>
                {comparisonData.map((row, index) => (
                  <tr key={row.feature} className="border-b border-border/50 last:border-0 hover:bg-beige/5 transition-colors">
                    <td className="py-6 px-6 font-bold text-foreground text-sm tracking-tight">{row.feature}</td>
                    <td className="py-6 px-6 text-center bg-beige/95 shadow-inner">
                      {renderCell(row.vocify, true)}
                    </td>
                    <td className="py-6 px-6 text-center text-muted-foreground hidden sm:table-cell">
                      {renderCell(row.traditional, false)}
                    </td>
                    <td className="py-6 px-6 text-center text-muted-foreground hidden md:table-cell">
                      {renderCell(row.voiceMemos, false)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ComparisonSection;
