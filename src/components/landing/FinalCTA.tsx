import { ArrowRight, Download, Mail } from "lucide-react";
import { Suspense, lazy } from "react";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";

const Object3D = lazy(() => import("./Object3D"));

const FinalCTA = () => {
  const { t } = useLanguage();

  return (
    <section className="relative overflow-hidden bg-ink py-28 text-cream md:py-36">
      <div className="container relative z-10 mx-auto px-6">
        <motion.div {...blurReveal()} className="mx-auto max-w-3xl text-center">
          <div className="relative mx-auto mb-6 h-56 max-w-md">
            <Suspense fallback={null}>
              <Object3D variant="ring" className="absolute inset-0" />
            </Suspense>
          </div>
          <h2 className="h-display mb-6 text-balance text-4xl md:text-6xl">
            {t.finalCta.title1} <br />
            <span className="accent-serif text-cream/70">{t.finalCta.title2}</span>
          </h2>
          <p className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-cream/60 md:text-xl">{t.finalCta.subtitle}</p>

          <div className="mx-auto mb-10 flex max-w-md flex-col items-center gap-5 rounded-3xl border border-white/10 bg-white/[0.03] p-8">
            <div>
              <p className="text-xl font-medium tracking-[-0.03em]">{t.finalCta.trial}</p>
              <p className="mt-1 text-sm text-cream/55">{t.finalCta.noCredit}</p>
            </div>
            <a
              href={DEMO_BOOKING_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-cream px-6 text-sm font-semibold text-ink transition-all duration-300 ease-silk hover:bg-white active:scale-[0.98]"
            >
              {t.finalCta.claim}
              <ArrowRight className="h-4 w-4 transition-transform duration-300 ease-silk group-hover:translate-x-0.5" />
            </a>
          </div>

          <div className="mb-10 flex flex-col items-center gap-2">
            <a
              href="/download/windows"
              className="inline-flex items-center gap-2 text-sm font-medium text-cream underline underline-offset-4 transition-colors hover:text-white"
            >
              <Download className="h-4 w-4" />
              {t.finalCta.windows}
            </a>
            <p className="max-w-sm text-xs text-cream/40">{t.finalCta.windowsNote}</p>
          </div>

          <div className="flex flex-col items-center gap-2">
            <div className="flex items-center gap-2 text-sm text-cream/60">
              <Mail className="h-4 w-4" />
              <span>
                {t.finalCta.questions}{" "}
                <a href="mailto:toni@getvocify.com" className="text-cream underline underline-offset-4 transition-colors hover:text-white">
                  toni@getvocify.com
                </a>
              </span>
            </div>
            <p className="text-xs text-cream/40">{t.finalCta.responseTime}</p>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default FinalCTA;
