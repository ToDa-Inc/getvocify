import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";
import { Check } from "lucide-react";
import { Suspense, lazy } from "react";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";

const Object3D = lazy(() => import("./Object3D"));

const PHASE_WIDTHS = [14, 38, 28, 20];
const OBJECTION_PHASE = 2;
const TREND_BEFORE = [52, 58, 55, 63, 66, 64, 71];

const sparkPath = (values: number[], w: number, h: number) => {
  const min = Math.min(...values) - 4;
  const max = Math.max(...values) + 4;
  return values.map((v, i) => `${i === 0 ? "M" : "L"}${(i / (values.length - 1)) * w},${h - ((v - min) / (max - min)) * h}`).join(" ");
};

const CoachingSection = () => {
  const { t } = useLanguage();
  const c = t.coaching;
  const reduced = useReducedMotion() ?? false;
  const steps: { name: string; value: number }[] = c.steps;
  const average = Math.round(steps.reduce((sum, s) => sum + s.value, 0) / steps.length);
  const trend = [...TREND_BEFORE, average];
  const weakest = steps.reduce((a, b) => (b.value < a.value ? b : a)).name;

  // the card leans toward the pointer
  const px = useSpring(useMotionValue(0), { stiffness: 120, damping: 18 });
  const py = useSpring(useMotionValue(0), { stiffness: 120, damping: 18 });
  const rotateY = useTransform(px, (v) => (reduced ? 0 : v));
  const rotateX = useTransform(py, (v) => (reduced ? 0 : v));

  return (
    <section id="coaching" className="relative scroll-mt-24 overflow-hidden bg-background py-28 md:py-36">
      <div className="container relative z-10 mx-auto px-6">
        <div className="grid items-center gap-14 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
          <motion.div {...blurReveal()}>
            <span className="section-label mb-6">02 — {c.label}</span>
            <h2 className="h-display mb-6 text-balance text-4xl text-foreground md:text-6xl">
              {c.title1} <span className="accent-serif">{c.title2}</span>
            </h2>
            <p className="mb-10 max-w-lg text-lg leading-relaxed text-muted-foreground">{c.subtitle}</p>
            <ul className="space-y-4">
              {c.points.map((point: string) => (
                <li key={point} className="flex items-start gap-3 text-base font-medium text-foreground/90">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-beige/10 text-beige">
                    <Check className="h-3 w-3" strokeWidth={3} />
                  </span>
                  {point}
                </li>
              ))}
            </ul>
          </motion.div>

          <motion.div
            {...blurReveal(0.1, 32, 0.96)}
            style={{ perspective: 1200 }}
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              px.set(((e.clientX - r.left) / r.width - 0.5) * 10);
              py.set(-((e.clientY - r.top) / r.height - 0.5) * 8);
            }}
            onPointerLeave={() => {
              px.set(0);
              py.set(0);
            }}
          >
            <motion.div
              style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}
              className="rounded-[28px] border border-border bg-white p-6 shadow-float md:p-8"
            >
              <p className="mb-6 text-sm font-medium text-foreground">{c.adherenceTitle}</p>

              <div className="mb-8 grid items-center gap-6 sm:grid-cols-[auto_1fr]" style={{ transform: "translateZ(30px)" }}>
                <div className="relative mx-auto h-44 w-44">
                  <Suspense fallback={null}>
                    <Object3D variant="gauge" value={average} className="absolute inset-0" />
                  </Suspense>
                  <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-4xl font-medium tracking-[-0.05em] text-foreground">{average}%</span>
                    <span className="text-xs text-muted-foreground">{c.team}</span>
                  </div>
                </div>
                <svg viewBox="0 0 240 70" className="h-20 w-full overflow-visible" preserveAspectRatio="none" aria-hidden>
                  <defs>
                    <linearGradient id="coach-spark" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" className="[stop-color:hsl(var(--beige))]" stopOpacity="0.25" />
                      <stop offset="1" className="[stop-color:hsl(var(--beige))]" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path d={`${sparkPath(trend, 240, 70)} L240,70 L0,70 Z`} fill="url(#coach-spark)" />
                  <motion.path
                    d={sparkPath(trend, 240, 70)}
                    fill="none"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="stroke-beige"
                    initial={{ pathLength: 0 }}
                    whileInView={{ pathLength: 1 }}
                    viewport={{ once: true, margin: "-60px" }}
                    transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
                  />
                </svg>
              </div>

              <ul className="mb-8 space-y-3.5" style={{ transform: "translateZ(18px)" }}>
                {steps.map((step, i) => {
                  const weak = step.name === weakest;
                  return (
                    <li key={step.name} className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-3 text-sm">
                      <span className="truncate font-medium text-foreground">{step.name}</span>
                      <span className="h-2 overflow-hidden rounded-full bg-beige/10">
                        <motion.span
                          initial={{ width: 0 }}
                          whileInView={{ width: `${step.value}%` }}
                          viewport={{ once: true, margin: "-60px" }}
                          transition={{ duration: 1, delay: 0.15 + i * 0.1, ease: [0.16, 1, 0.3, 1] }}
                          className={`block h-full rounded-full ${weak ? "bg-warning" : "bg-beige"}`}
                        />
                      </span>
                      <span className="flex items-center gap-2 text-xs text-muted-foreground">
                        {weak && (
                          <span className="rounded-full bg-warning/15 px-2 py-0.5 text-xs text-foreground">{c.weak}</span>
                        )}
                        {step.value}%
                      </span>
                    </li>
                  );
                })}
              </ul>

              <div style={{ transform: "translateZ(10px)" }}>
                <p className="mb-3 text-sm font-medium text-foreground">{c.timelineTitle}</p>
                <div className="flex gap-1.5">
                  {c.phases.map((phase: string, i: number) => (
                    <div key={phase} style={{ width: `${PHASE_WIDTHS[i]}%` }} className="min-w-0">
                      <div className={`h-2 rounded-full ${i === OBJECTION_PHASE ? "bg-warning" : "bg-beige/15"}`} />
                      <p className={`mt-2 truncate text-xs ${i === OBJECTION_PHASE ? "text-foreground" : "text-muted-foreground/60"}`}>
                        {phase}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 rounded-2xl bg-beige/10 p-4">
                  <p className="text-sm font-medium text-foreground">{c.moment}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{c.fix}</p>
                </div>
              </div>
              <p className="mt-6 text-xs text-muted-foreground/70">{c.sample}</p>
            </motion.div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default CoachingSection;
