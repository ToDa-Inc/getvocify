import { ArrowRight, Check, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const Pricing = () => {
  const { t } = useLanguage();

  const plans = [
    {
      name: t.pricing.p1.name,
      price: t.pricing.p1.price,
      period: t.pricing.p1.period,
      description: t.pricing.p1.desc,
      features: t.pricing.p1.features,
      cta: t.pricing.p1.cta,
      popular: false,
    },
    {
      name: t.pricing.p2.name,
      price: t.pricing.p2.price,
      period: t.pricing.p2.period,
      description: t.pricing.p2.desc,
      features: t.pricing.p2.features,
      cta: t.pricing.p2.cta,
      popular: true,
    },
    {
      name: t.pricing.p3.name,
      price: t.pricing.p3.price,
      period: t.pricing.p3.period,
      description: t.pricing.p3.desc,
      features: t.pricing.p3.features,
      cta: t.pricing.p3.cta,
      popular: false,
    },
  ];

  return (
    <section id="pricing" className="py-32 bg-background relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-20">
          <motion.h2 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            className="text-3xl md:text-5xl font-bold text-foreground mb-6 tracking-tight"
          >
            {t.pricing.title1} <span className="text-beige font-black">{t.pricing.title2}</span>
          </motion.h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t.pricing.subtitle}
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto mb-12">
          {plans.map((plan, index) => (
            <motion.div
              key={plan.name}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ delay: index * 0.1 }}
              className={`relative glass-morphism rounded-[3rem] p-10 flex flex-col hover:shadow-medium transition-all duration-500 hover:-translate-y-2 ${
                plan.popular ? "border-beige/40 ring-1 ring-beige/20 shadow-medium" : "border-border/50"
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-beige text-cream text-[10px] font-bold uppercase tracking-[0.2em] px-4 py-1.5 rounded-full flex items-center gap-2 shadow-soft">
                  <Sparkles className="w-3 h-3" />
                  {t.pricing.popular}
                </div>
              )}
              
              <div className="text-center mb-10">
                <h3 className="text-sm font-bold tracking-[0.3em] uppercase text-beige mb-6">{plan.name}</h3>
                <div className="flex items-baseline justify-center gap-1 mb-4">
                  <span className="text-5xl font-bold text-foreground tracking-tight">{plan.price}</span>
                  <span className="text-sm text-muted-foreground font-medium">{plan.period}</span>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">{plan.description}</p>
              </div>

              <ul className="space-y-4 mb-10 flex-1">
                {plan.features.map((feature: string) => (
                  <li key={feature} className="flex items-center gap-3 text-sm">
                    <div className="w-5 h-5 rounded-full bg-green-500/10 flex items-center justify-center flex-shrink-0">
                      <Check className="w-3 h-3 text-green-600" />
                    </div>
                    <span className="text-foreground font-medium">{feature}</span>
                  </li>
                ))}
              </ul>

              <Button
                variant={plan.popular ? "hero" : "outline"}
                size="xl"
                className={`w-full group rounded-[2rem] shadow-soft ${plan.popular ? "" : "bg-white hover:bg-beige/5"}`}
                asChild
              >
                <Link to="/dashboard">
                  {plan.cta}
                  <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                </Link>
              </Button>
            </motion.div>
          ))}
        </div>

        <motion.p 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-center text-xs font-bold uppercase tracking-widest text-muted-foreground/60"
        >
          {t.pricing.badge1} <span className="text-beige font-black">{t.pricing.badge2}</span>
        </motion.p>
      </div>
    </section>
  );
};

export default Pricing;
