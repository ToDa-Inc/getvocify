import { lazy, Suspense } from "react";
import { motion } from "framer-motion";
import { Car, Cpu, Globe, ShieldOff, type LucideIcon } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";
const Object3D = lazy(() => import("./Object3D"));

const CARD_ICONS: LucideIcon[] = [ShieldOff, Cpu, Car];

const Card = ({ className = "", children }: { className?: string; children: React.ReactNode }) => (
  <div className={`relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] p-7 md:p-8 ${className}`}>
    <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
    {children}
  </div>
);

const CaptureSection = () => {
  const { t } = useLanguage();
  const c = t.capture;

  return (
    <section id="capture" className="relative scroll-mt-24 overflow-hidden bg-ink py-28 text-cream md:py-36">
      <div className="container relative z-10 mx-auto px-6">
        <motion.div {...blurReveal()} className="mx-auto mb-16 max-w-3xl text-center">
          <span className="section-label mb-6 text-cream/60">03 — {c.label}</span>
          <h2 className="h-display mb-6 text-balance text-4xl md:text-6xl">
            {c.title1} <span className="accent-serif text-cream/80">{c.title2}</span>
          </h2>
          <p className="text-lg leading-relaxed text-cream/60 md:text-xl">{c.subtitle}</p>
        </motion.div>

        <div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-3">
          <motion.div {...blurReveal(0, 28, 0.97)} className="md:col-span-2">
            <Card className="grid h-full items-center gap-8 md:grid-cols-[1fr_auto]">
              <div>
                <h3 className="mb-3 text-2xl font-medium tracking-[-0.03em]">{c.cube.title}</h3>
                <p className="max-w-sm text-base leading-relaxed text-cream/60">{c.cube.desc}</p>
              </div>
              <Suspense fallback={<div className="h-72 w-full md:w-[22rem]" />}>
                <Object3D variant="ring" className="h-72 w-full md:w-[22rem]" />
              </Suspense>
            </Card>
          </motion.div>

          {c.cards.map((card: { title: string; desc: string }, i: number) => {
            const Icon = CARD_ICONS[i];
            return (
              <motion.div key={card.title} {...blurReveal((i + 1) * 0.07, 28, 0.97)} >
                <Card className="h-full">
                  <span className="mb-6 flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-beige-light">
                    <Icon className="h-5 w-5" strokeWidth={1.5} />
                  </span>
                  <h3 className="mb-2 text-xl font-medium tracking-[-0.03em]">{card.title}</h3>
                  <p className="text-[15px] leading-relaxed text-cream/60">{card.desc}</p>
                </Card>
              </motion.div>
            );
          })}

          <motion.div {...blurReveal(0.28, 28, 0.97)}>
            <Card className="h-full">
              <span className="mb-6 flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-beige-light">
                <Globe className="h-5 w-5" strokeWidth={1.5} />
              </span>
              <h3 className="mb-2 text-xl font-medium tracking-[-0.03em]">{c.languages}</h3>
              <p className="text-[15px] leading-relaxed text-cream/60">{c.languagesList}</p>
            </Card>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default CaptureSection;
