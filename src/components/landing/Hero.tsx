import { ArrowRight, Play } from "lucide-react";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { motion } from "framer-motion";
import IslandDemo from "./IslandDemo";
import IntegrationsCarousel from "./IntegrationsCarousel";
import { useLanguage } from "@/lib/i18n";
import { useDemoVideo } from "@/contexts/DemoVideoContext";

const Hero = () => {
  const { t } = useLanguage();
  const { openDemo } = useDemoVideo();

  return (
    <section className="relative bg-ink pt-36 text-cream sm:pt-44">
      <div className="container relative z-10 mx-auto px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="mx-auto mb-16 max-w-5xl text-center"
        >
          <h1 className="mb-7 text-balance font-serif text-[clamp(3.4rem,8.5vw,7rem)] font-normal leading-[0.96] tracking-[-0.02em] text-cream">
            {t.hero.title1}
            <br />
            {t.hero.title2Prefix}{" "}
            <span className="chip-glow font-sans text-[0.62em] font-medium tracking-[-0.04em]">{t.hero.title2Word}</span>
          </h1>
          <p className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-cream/65 md:text-xl">
            {t.hero.subtitle1} <br className="hidden md:block" />
            <span className="font-medium text-cream">{t.hero.subtitle2}</span> {t.hero.subtitle3}
          </p>
          <div className="mb-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href={DEMO_BOOKING_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-cream px-6 text-sm font-semibold text-ink transition-all duration-300 ease-silk hover:bg-white active:scale-[0.98] sm:w-auto"
            >
              {t.hero.cta1}
              <ArrowRight className="h-4 w-4 transition-transform duration-300 ease-silk group-hover:translate-x-0.5" />
            </a>
            <button
              type="button"
              onClick={() => openDemo()}
              className="group inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl border-2 border-white/10 px-6 text-sm font-semibold text-cream transition-all duration-300 ease-silk hover:bg-white/5 active:scale-[0.98] sm:w-auto"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              {t.hero.cta2}
            </button>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-4 text-xs font-medium text-cream/45 md:gap-8">
            {[t.hero.trust1, t.hero.trust2, t.hero.trust3].map((trust: string) => (
              <span key={trust} className="flex items-center gap-2">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/10 text-[8px] text-cream/80">✓</span>
                {trust}
              </span>
            ))}
          </div>
        </motion.div>

        <motion.div
          id="how-it-works"
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
          className="mx-auto max-w-5xl scroll-mt-24"
        >
          <IslandDemo />
        </motion.div>
      </div>

      <IntegrationsCarousel />
    </section>
  );
};

export default Hero;
