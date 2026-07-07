import { ArrowRight, Play } from "lucide-react";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { motion } from "framer-motion";
import WaveformCircle from "./WaveformCircle";
import RotatingText from "./RotatingText";
import IntegrationsCarousel from "./IntegrationsCarousel";
import { useLanguage } from "@/lib/i18n";
import { useDemoVideo } from "@/contexts/DemoVideoContext";

const Hero = () => {
  const { t } = useLanguage();
  const { openDemo } = useDemoVideo();

  return (
    <section className="relative flex min-h-[100svh] flex-col items-center justify-start overflow-hidden bg-mesh-gradient pt-40 pb-16 sm:pt-44">
      <div className="container relative z-10 mx-auto flex flex-col items-center justify-center px-6 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="mx-auto mb-16 max-w-6xl"
        >
          {/* Headline */}
          <h1 className="mb-7 text-[clamp(3rem,7vw,5.5rem)] font-semibold tracking-[-0.045em] leading-[0.95] text-balance">
            {t.hero.title1}
            <br />
            {t.hero.title2Prefix}{" "}
            <span className="chip-glow text-[0.82em] font-semibold tracking-[-0.03em]">{t.hero.title2Word}</span>
          </h1>

          {/* Subheadline */}
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
            className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-muted-foreground md:text-xl"
          >
            {t.hero.subtitle1}{" "}
            <br className="hidden md:block" />
            <span className="font-serif italic font-medium">{t.hero.subtitle2}</span> {t.hero.subtitle3}
          </motion.p>

          {/* CTA Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
            className="mb-12 flex flex-col items-center justify-center gap-4 sm:flex-row"
          >
            <a
              href={DEMO_BOOKING_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-glow transition-snap group inline-flex w-full items-center justify-center gap-3 rounded-full bg-beige py-3 pl-7 pr-3 text-sm font-semibold text-cream hover:bg-beige-dark active:scale-[0.98] sm:w-auto"
            >
              {t.hero.cta1}
              <span className="flex size-9 items-center justify-center rounded-full bg-cream text-beige transition-transform duration-500 ease-silk group-hover:translate-x-0.5 group-hover:-translate-y-px group-hover:scale-105">
                <ArrowRight className="h-4 w-4" />
              </span>
            </a>
            <button
              type="button"
              onClick={() => openDemo()}
              className="glass-card transition-snap group inline-flex w-full items-center justify-center gap-3 rounded-full py-3 pl-3 pr-7 text-sm font-semibold text-stone-800 hover:bg-white/80 hover:text-stone-950 active:scale-[0.98] sm:w-auto"
            >
              <span className="flex size-9 items-center justify-center rounded-full bg-beige/10 text-beige transition-transform duration-500 ease-silk group-hover:scale-105">
                <Play className="h-4 w-4 fill-current" />
              </span>
              {t.hero.cta2}
            </button>
          </motion.div>

          {/* Trust Bar */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 0.8 }}
            className="mb-16 flex flex-wrap items-center justify-center gap-4 font-mono text-[11px] font-bold uppercase tracking-[0.06em] text-muted-foreground/70 md:gap-8"
          >
            {[t.hero.trust1, t.hero.trust2, t.hero.trust3].map((trust, i) => (
              <span key={i} className="flex items-center gap-2">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-success/10 text-[8px] font-bold text-success">
                  ✓
                </span>
                {trust}
              </span>
            ))}
          </motion.div>

          {/* Waveform Circle with Rotating Text */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, delay: 0.6, ease: "circOut" }}
            className="group relative mx-auto h-64 w-64 cursor-pointer md:h-80 md:w-80"
          >
            <RotatingText />
            <WaveformCircle />
          </motion.div>
        </motion.div>
      </div>

      <IntegrationsCarousel />

      {/* Background elements */}
      <div className="absolute top-1/4 -left-20 -z-10 h-96 w-96 animate-pulse-wave rounded-full bg-beige/5 blur-[100px]" />
      <div
        className="absolute bottom-1/4 -right-20 -z-10 h-96 w-96 animate-pulse-wave rounded-full bg-accent/5 blur-[100px]"
        style={{ animationDelay: "1s" }}
      />
    </section>
  );
};

export default Hero;
