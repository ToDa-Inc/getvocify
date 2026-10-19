import { ArrowRight } from "lucide-react";
import { motion } from "framer-motion";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";

const PricingSection = () => {
  const { t } = useLanguage();

  return (
    <section id="pricing" className="relative scroll-mt-24 overflow-hidden bg-ink py-28 text-cream md:py-36">
      <div className="container mx-auto px-6 relative z-10">
        <motion.div {...blurReveal()} className="mx-auto max-w-3xl text-center">
          <span className="section-label mb-6 text-cream/60">05 — {t.pricing.label}</span>
          <h2 className="h-display mb-6 text-4xl md:text-6xl">
            {t.pricing.title1}{" "}
            <span className="accent-serif text-cream/70">{t.pricing.title2}</span>
          </h2>
          <p className="mx-auto mb-10 max-w-2xl text-lg text-cream/60">{t.pricing.subtitle}</p>
          <a
            href={DEMO_BOOKING_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="group inline-flex h-12 items-center justify-center gap-2 rounded-2xl bg-cream px-8 text-sm font-semibold text-ink transition-all duration-300 ease-silk hover:bg-white active:scale-[0.98]"
          >
            {t.pricing.cta}
            <ArrowRight className="h-4 w-4 transition-transform duration-300 ease-silk group-hover:translate-x-0.5" />
          </a>
        </motion.div>
      </div>
    </section>
  );
};

export default PricingSection;
