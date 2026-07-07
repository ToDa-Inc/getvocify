import { ArrowRight, Play, Mail } from "lucide-react";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import { useDemoVideo } from "@/contexts/DemoVideoContext";

const FinalCTA = () => {
  const { t } = useLanguage();
  const { openDemo } = useDemoVideo();
  
  return (
    <section className="py-32 bg-ink relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-4xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="mb-12"
          >
            <h2 className="text-4xl md:text-6xl font-semibold text-cream mb-8 tracking-tighter leading-[1.02] text-balance">
              {t.finalCta.title1} <br />
              <span className="text-white font-serif italic font-medium">{t.finalCta.title2}</span>
            </h2>
            <p className="text-cream/80 text-lg md:text-xl mb-12 max-w-2xl mx-auto leading-relaxed">
              {t.finalCta.subtitle}
            </p>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="glass-card-dark rounded-[28px] p-10 md:p-16 mb-16"
          >
            <div className="grid md:grid-cols-2 gap-12 items-center">
              <div className="text-left">
                <p className="text-cream font-mono font-medium uppercase tracking-[0.25em] text-xs mb-8 opacity-60">{t.finalCta.onboarding}</p>
                <ol className="space-y-6">
                  {t.finalCta.steps.map((step: string, index: number) => (
                    <li key={index} className="flex items-start gap-4 text-cream">
                      <span className="flex-shrink-0 w-8 h-8 rounded-full bg-cream/10 flex items-center justify-center text-xs font-bold border border-cream/20">
                        {index + 1}
                      </span>
                      <span className="text-lg font-medium opacity-90 leading-tight">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
              <div className="relative">
                <div className="aspect-square rounded-[24px] glass-card-dark flex flex-col items-center justify-center p-8 text-cream">
                  <div className="w-20 h-20 rounded-full bg-cream flex items-center justify-center mb-6 shadow-[0_0_40px_-8px_hsl(40_33%_96%/0.4)]">
                    <ArrowRight className="w-10 h-10 text-beige" />
                  </div>
                  <p className="text-2xl font-serif italic font-medium mb-2">{t.finalCta.trial}</p>
                  <p className="text-sm opacity-60">{t.finalCta.noCredit}</p>
                </div>
                {/* Decorative glow */}
                <div className="absolute inset-8 bg-beige/20 rounded-full blur-[100px] -z-10" />
              </div>
            </div>
          </motion.div>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 mb-16">
            <a
              href={DEMO_BOOKING_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex w-full items-center justify-center gap-3 rounded-full bg-cream py-3 pl-7 pr-3 text-sm font-semibold text-ink transition-all duration-500 ease-silk hover:bg-white active:scale-[0.98] sm:w-auto shadow-[inset_0_1px_0_rgba(255,255,255,0.6),0_0_40px_-10px_hsl(40_33%_96%/0.5)]"
            >
              {t.finalCta.claim}
              <span className="flex size-9 items-center justify-center rounded-full bg-beige text-cream transition-transform duration-500 ease-silk group-hover:translate-x-0.5 group-hover:-translate-y-px group-hover:scale-105">
                <ArrowRight className="h-4 w-4" />
              </span>
            </a>
            <button
              type="button"
              onClick={() => openDemo()}
              className="glass-card-dark group inline-flex w-full items-center justify-center gap-3 rounded-full py-3 pl-3 pr-7 text-sm font-semibold text-cream transition-all duration-500 ease-silk hover:bg-white/10 active:scale-[0.98] sm:w-auto"
            >
              <span className="flex size-9 items-center justify-center rounded-full bg-cream/10 text-cream transition-transform duration-500 ease-silk group-hover:scale-105">
                <Play className="h-4 w-4 fill-current" />
              </span>
              {t.finalCta.watch}
            </button>
          </div>

          <div className="flex flex-col items-center gap-4">
            <div className="flex items-center gap-2 text-cream/70 text-sm font-medium">
              <Mail className="w-4 h-4" />
              <span>
                {t.finalCta.questions}{" "}
                <a
                  href="mailto:toni@getvocify.com"
                  className="text-cream underline underline-offset-4 hover:text-white transition-colors"
                >
                  toni@getvocify.com
                </a>
              </span>
            </div>
            <p className="text-cream/40 font-mono text-[10px] uppercase tracking-[0.2em] font-medium">
              {t.finalCta.responseTime}
            </p>
          </div>
        </div>
      </div>
      
      {/* Background decoration */}
      <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-white/5 rounded-full blur-[150px] -z-10" />
      <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-white/5 rounded-full blur-[150px] -z-10" />
    </section>
  );
};

export default FinalCTA;
