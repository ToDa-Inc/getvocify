import { Clock, Sparkles, Smartphone, Activity, Globe, ShieldCheck } from "lucide-react";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const Features = () => {
  const { t } = useLanguage();

  const features = [
    {
      icon: Clock,
      title: t.features.f1.title,
      description: t.features.f1.desc,
      color: "#D97706", // amber-600
    },
    {
      icon: Sparkles,
      title: t.features.f2.title,
      description: t.features.f2.desc,
      color: "#2563EB", // blue-600
    },
    {
      icon: Smartphone,
      title: t.features.f3.title,
      description: t.features.f3.desc,
      color: "#7C3AED", // purple-600
    },
    {
      icon: Activity,
      title: t.features.f4.title,
      description: t.features.f4.desc,
      color: "#059669", // emerald-600
    },
    {
      icon: Globe,
      title: t.features.f5.title,
      description: t.features.f5.desc,
      color: "#EA580C", // orange-600
    },
    {
      icon: ShieldCheck,
      title: t.features.f6.title,
      description: t.features.f6.desc,
      color: "#475569", // slate-600
    },
  ];
  
  return (
    <section id="features" className="py-32 bg-white relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-20">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.8 }}
              >
                <h2 className="text-4xl md:text-5xl font-black text-foreground mb-6 tracking-tighter leading-tight">
                  {t.features.title1} <br />
                  <span className="text-beige font-black">{t.features.title2}</span>
                </h2>
                <p className="text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
                  {t.features.subtitle}
                </p>
              </motion.div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 max-w-6xl mx-auto">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              whileHover={{ y: -5 }}
              className="p-8 rounded-[2rem] border border-border/50 bg-secondary/5 hover:bg-white hover:border-beige/30 transition-all duration-300 group will-change-transform"
            >
              <div 
                className="w-12 h-12 rounded-2xl flex items-center justify-center mb-6 shadow-soft group-hover:scale-110 transition-transform"
                style={{ backgroundColor: `${feature.color}15` }}
              >
                <feature.icon className="w-6 h-6" style={{ color: feature.color }} strokeWidth={1.5} />
              </div>
              <h3 className="text-[10px] font-black uppercase tracking-[0.3em] text-foreground/40 mb-3 group-hover:text-foreground transition-colors">
                {feature.title}
              </h3>
              <p className="text-base font-bold text-foreground/80 leading-snug group-hover:text-foreground transition-colors">
                {feature.description}
              </p>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Subtle background accents */}
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-beige/5 rounded-full blur-[120px] -z-10" />
      <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-accent/5 rounded-full blur-[100px] -z-10" />
    </section>
  );
};

export default Features;
