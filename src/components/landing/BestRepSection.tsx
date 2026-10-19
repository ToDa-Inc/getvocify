import { motion, useReducedMotion, useScroll, useTransform, type MotionValue } from "framer-motion";
import { useRef } from "react";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";

const Word = ({
  children,
  range,
  progress,
  accent,
  still,
}: {
  children: string;
  range: [number, number];
  progress: MotionValue<number>;
  accent: boolean;
  still: boolean;
}) => {
  const opacity = useTransform(progress, range, [0.16, 1]);
  return (
    <motion.span
      style={still ? undefined : { opacity }}
      className={accent ? "text-beige-light" : undefined}
    >
      {children}{" "}
    </motion.span>
  );
};

const BestRepSection = () => {
  const { t } = useLanguage();
  const ref = useRef<HTMLDivElement>(null);
  const still = useReducedMotion() ?? false;
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.85", "end 0.55"] });

  const lead: string[] = t.bestRep.title1.split(" ");
  const accent: string[] = t.bestRep.title2.split(" ");
  const words = [...lead.map((w) => ({ w, accent: false })), ...accent.map((w) => ({ w, accent: true }))];

  return (
    <section className="relative bg-ink py-24 text-cream md:py-32">
      <div className="container mx-auto px-6">
        <div ref={ref} className="mx-auto max-w-5xl text-center">
          <span className="section-label mb-8 text-cream/60">{t.bestRep.label}</span>
          <h2 className="h-display text-balance text-4xl text-cream md:text-6xl">
            {words.map(({ w, accent: isAccent }, i) => (
              <Word
                key={`${w}-${i}`}
                range={[i / words.length, Math.min(1, (i + 2) / words.length)]}
                progress={scrollYProgress}
                accent={isAccent}
                still={still}
              >
                {w}
              </Word>
            ))}
          </h2>
          <motion.p
            {...blurReveal(0.1, 16, 0.98)}
            className="mx-auto mt-10 max-w-2xl text-lg leading-relaxed text-cream/60 md:text-xl"
          >
            {t.bestRep.body}
          </motion.p>
        </div>
      </div>
    </section>
  );
};

export default BestRepSection;
