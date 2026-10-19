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
    <section id="pricing" className="relative scroll-mt-24 overflow-hidden bg-ink py-28 text-cream md:py-36">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}>
            <span className="section-label mb-6 text-cream/60">05 — {t.pricing.label}</span>
            <h2 className="h-display mb-6 text-4xl md:text-6xl">
              {t.pricing.title1}{" "}
              <span className="accent-serif text-cream/70">{t.pricing.title2}</span>
            </h2>
            <p className="mx-auto max-w-2xl text-lg text-cream/60">{t.pricing.subtitle}</p>
          </motion.div>
        </div>

        <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
          {plans.map(({ plan, highlighted }, index) => (
            <motion.div
              key={plan.id}
              {...blurReveal(index * 0.08, 24, 0.97)}
              className={`relative flex flex-col overflow-hidden rounded-3xl border p-8 md:p-10 ${
                highlighted ? "border-beige/40 bg-white/[0.05]" : "border-white/10 bg-white/[0.03]"
              }`}
            >
              <div className="mb-6">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <p className="text-lg font-medium text-cream">{plan.name}</p>
                  {highlighted ? (
                    <span className="text-xs text-beige-light">
                      {t.pricing.proBadge}
                    </span>
                  ) : null}
                </div>
                <p className="text-sm text-cream/55">{plan.id === "starter" ? t.pricing.starterTagline : t.pricing.proTagline}</p>
              </div>

              <div className="mb-6">
                <p className="text-[2.5rem] leading-none tracking-[-0.04em] text-cream">
                  €{plan.monthlyAmount}
                  <span className="text-base font-normal text-cream/55"> {t.pricing.perMonth}</span>
                </p>
                <p className="mt-2 text-sm text-cream/55">
                  {t.pricing.orYearly
                    .replace("{yearly}", String(plan.yearlyAmount))
                    .replace("{monthly}", String(plan.yearlyMonthlyAmount))}
                </p>
              </div>

              <ul className="space-y-3 mb-8 flex-1">
                {(plan.id === "starter" ? t.pricing.starterFeatures : t.pricing.proFeatures).map(
                  (feature: string) => (
                    <li key={feature} className="flex items-start gap-2.5 text-sm text-cream/90">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-beige-light" />
                      <span>{feature}</span>
                    </li>
                  ),
                )}
              </ul>

              <a
                href={DEMO_BOOKING_URL}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex h-12 w-full items-center justify-center rounded-2xl text-sm font-semibold transition-all duration-300 ease-silk active:scale-[0.98] ${
                  highlighted ? "bg-cream text-ink hover:bg-white" : "border-2 border-white/10 text-cream hover:bg-white/5"
                }`}
              >
                {t.pricing.cta}
              </a>
            </motion.div>
          ))}
        </div>

        <p className="mx-auto mt-8 max-w-xl text-center text-sm text-cream/45">{t.pricing.note}</p>
      </div>
    </section>
  );
};

export default PricingSection;
