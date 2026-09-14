import { Check } from "lucide-react";
import { motion } from "framer-motion";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";
import { FALLBACK_PLANS } from "@/features/billing/api";

const PricingSection = () => {
  const { t } = useLanguage();
  const starter = FALLBACK_PLANS.find((plan) => plan.id === "starter")!;
  const pro = FALLBACK_PLANS.find((plan) => plan.id === "pro")!;

  const plans = [
    { plan: starter, highlighted: false },
    { plan: pro, highlighted: true },
  ];

  return (
    <section id="pricing" className="scroll-mt-24 py-32 bg-background relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}>
            <span className="section-label mb-6">07 — {t.pricing.label}</span>
            <h2 className="text-3xl md:text-5xl font-semibold text-foreground mb-6 tracking-tighter">
              {t.pricing.title1}{" "}
              <span className="text-beige font-serif italic font-medium">{t.pricing.title2}</span>
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">{t.pricing.subtitle}</p>
          </motion.div>
        </div>

        <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
          {plans.map(({ plan, highlighted }, index) => (
            <motion.div
              key={plan.id}
              {...blurReveal(index * 0.08, 24, 0.97)}
              className={`glass-card rounded-[28px] p-8 md:p-10 flex flex-col ${
                highlighted ? "border border-beige/30 shadow-float" : ""
              }`}
            >
              <div className="mb-6">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <p className="font-semibold text-foreground text-lg">{plan.name}</p>
                  {highlighted ? (
                    <span className="text-[11px] font-mono uppercase tracking-[0.15em] text-beige">
                      {t.pricing.proBadge}
                    </span>
                  ) : null}
                </div>
                <p className="text-sm text-muted-foreground">{plan.tagline}</p>
              </div>

              <div className="mb-6">
                <p className="text-[2.5rem] leading-none tracking-tight text-foreground">
                  €{plan.monthlyAmount}
                  <span className="text-base text-muted-foreground font-normal"> {t.pricing.perMonth}</span>
                </p>
                <p className="text-sm text-muted-foreground mt-2">
                  {t.pricing.orYearly
                    .replace("{yearly}", String(plan.yearlyAmount))
                    .replace("{monthly}", String(plan.yearlyMonthlyAmount))}
                </p>
              </div>

              <ul className="space-y-3 mb-8 flex-1">
                {(plan.id === "starter" ? t.pricing.starterFeatures : t.pricing.proFeatures).map(
                  (feature: string) => (
                    <li key={feature} className="flex items-start gap-2.5 text-sm text-foreground">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-beige" />
                      <span>{feature}</span>
                    </li>
                  ),
                )}
              </ul>

              <a
                href={DEMO_BOOKING_URL}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex w-full items-center justify-center rounded-full py-3 text-sm font-semibold transition-all duration-500 ease-silk active:scale-[0.98] ${
                  highlighted
                    ? "bg-beige text-cream hover:bg-beige-dark"
                    : "border border-border/60 text-foreground hover:bg-beige/5"
                }`}
              >
                {t.pricing.cta}
              </a>
            </motion.div>
          ))}
        </div>

        <p className="text-center text-sm text-muted-foreground mt-8 max-w-xl mx-auto">{t.pricing.note}</p>
      </div>
    </section>
  );
};

export default PricingSection;
