import { Car, Phone, Stethoscope, Building, Briefcase, GraduationCap, ChevronRight, ChevronLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { useLanguage } from "@/lib/i18n";

const UseCasesSection = () => {
  const { t } = useLanguage();
  const [active, setActive] = useState(0);

  const useCases = [
    {
      icon: Car,
      title: t.useCases.uc1.title,
      description: t.useCases.uc1.desc,
      color: "#3B82F6", // blue-500
      tag: t.useCases.uc1.tag
    },
    {
      icon: Building,
      title: t.useCases.uc2.title,
      description: t.useCases.uc2.desc,
      color: "#8B5CF6", // purple-500
      tag: t.useCases.uc2.tag
    },
    {
      icon: Stethoscope,
      title: t.useCases.uc3.title,
      description: t.useCases.uc3.desc,
      color: "#10B981", // emerald-500
      tag: t.useCases.uc3.tag
    },
    {
      icon: Phone,
      title: t.useCases.uc4.title,
      description: t.useCases.uc4.desc,
      color: "#F59E0B", // amber-500
      tag: t.useCases.uc4.tag
    },
    {
      icon: Briefcase,
      title: t.useCases.uc5.title,
      description: t.useCases.uc5.desc,
      color: "#F97316", // orange-500
      tag: t.useCases.uc5.tag
    },
    {
      icon: GraduationCap,
      title: t.useCases.uc6.title,
      description: t.useCases.uc6.desc,
      color: "#64748B", // slate-500
      tag: t.useCases.uc6.tag
    },
  ];

  return (
    <section className="py-40 bg-secondary/5 relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="flex flex-col lg:flex-row gap-20 items-center">
          <div className="lg:w-1/2">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8 }}
            >
              <h2 className="text-4xl md:text-6xl font-black text-foreground mb-8 tracking-tighter leading-none">
                {t.useCases.title1} <br />
                <span className="font-serif italic font-medium text-beige">{t.useCases.title2}</span>
              </h2>
              <p className="text-xl text-muted-foreground max-w-lg leading-relaxed mb-12">
                {t.useCases.subtitle}
              </p>

              <div className="flex flex-wrap gap-4">
                {useCases.map((useCase, index) => (
                  <button
                    key={index}
                    onClick={() => setActive(index)}
                    className={`px-6 py-3 rounded-full text-sm font-black uppercase tracking-widest transition-all duration-300 border ${
                      active === index 
                        ? "bg-beige border-beige text-cream shadow-medium" 
                        : "bg-white border-border/50 text-muted-foreground hover:border-beige/50"
                    }`}
                  >
                    {useCase.title}
                  </button>
                ))}
              </div>
            </motion.div>
          </div>

          <div className="lg:w-1/2 relative h-[500px] w-full max-w-2xl">
            <AnimatePresence mode="wait">
              <motion.div
                key={active}
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 1.05, y: -20 }}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className="absolute inset-0"
              >
                <div className="h-full w-full bg-white rounded-[3.5rem] p-12 md:p-16 shadow-large border border-beige/10 flex flex-col justify-between overflow-hidden group">
                  {/* Glassmorphic Icon */}
                  <div 
                    className="w-20 h-20 rounded-3xl flex items-center justify-center mb-12 transition-all duration-500 shadow-soft"
                    style={{ backgroundColor: `${useCases[active].color}10` }}
                  >
                    {(() => {
                      const Icon = useCases[active].icon;
                      return <Icon className="w-10 h-10" style={{ color: useCases[active].color }} />;
                    })()}
                  </div>

                  <div className="space-y-6">
                    <span className="inline-block text-[10px] font-black uppercase tracking-[0.4em] text-beige">
                      {useCases[active].tag}
                    </span>
                    <h3 className="text-3xl md:text-4xl font-black text-foreground tracking-tight">
                      {useCases[active].title}
                    </h3>
                    <p className="text-xl text-muted-foreground leading-relaxed font-medium">
                      {useCases[active].description}
                    </p>
                  </div>

                  <div className="flex items-center gap-4 pt-12">
                    <button 
                      onClick={() => setActive((prev) => (prev === 0 ? useCases.length - 1 : prev - 1))}
                      className="p-4 rounded-full border border-border/50 hover:border-beige transition-colors"
                    >
                      <ChevronLeft className="w-5 h-5 text-beige" />
                    </button>
                    <button 
                      onClick={() => setActive((prev) => (prev === useCases.length - 1 ? 0 : prev + 1))}
                      className="p-4 rounded-full border border-border/50 hover:border-beige transition-colors"
                    >
                      <ChevronRight className="w-5 h-5 text-beige" />
                    </button>
                    <div className="flex-1" />
                    <span className="text-[10px] font-black text-muted-foreground/30 uppercase tracking-widest">
                      {active + 1} / {useCases.length}
                    </span>
                  </div>

                  {/* Decorative background shape */}
                  <div 
                    className="absolute -top-24 -right-24 w-64 h-64 blur-[80px] opacity-10 rounded-full"
                    style={{ backgroundColor: useCases[active].color }}
                  />
                </div>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
};

export default UseCasesSection;
