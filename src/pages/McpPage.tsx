import { Suspense, lazy, useEffect } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Plus } from "lucide-react";
import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";
import { ChatGptMark, ClaudeMark, CursorMark } from "@/components/landing/brand-icons";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { useLanguage } from "@/lib/i18n";
import { mcpCopy } from "@/lib/landing-mcp";
import { blurReveal } from "@/lib/scrollReveal";

const Object3D = lazy(() => import("@/components/landing/Object3D"));

const MARKS = [ClaudeMark, CursorMark, ChatGptMark];

const CtaButton = ({ children, tone }: { children: React.ReactNode; tone: "light" | "ghost" }) => (
  <a
    href={DEMO_BOOKING_URL}
    target="_blank"
    rel="noopener noreferrer"
    className={`group inline-flex h-12 items-center justify-center gap-2 rounded-2xl px-6 text-sm font-semibold transition-all duration-300 ease-silk active:scale-[0.98] ${
      tone === "light" ? "bg-cream text-ink hover:bg-white" : "border-2 border-white/10 text-cream hover:bg-white/5"
    }`}
  >
    {children}
    <ArrowRight className="h-4 w-4 transition-transform duration-300 ease-silk group-hover:translate-x-0.5" />
  </a>
);

const McpPage = () => {
  const { language } = useLanguage();
  const c = mcpCopy[language];

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  return (
    <div className="min-h-screen bg-ink text-cream">
      <Header />
      <main>
        <section className="relative overflow-hidden px-6 pb-24 pt-40 text-center md:pb-32 md:pt-48">
          <motion.div {...blurReveal(0, 20, 0.98)} className="relative mx-auto max-w-4xl">
            <span className="mb-8 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-cream/70">
              <span className="h-1.5 w-1.5 rounded-full bg-beige-light" />
              {c.eyebrow} · {c.badge}
            </span>
            <h1 className="mb-7 text-balance font-serif text-[clamp(3.2rem,8vw,6.5rem)] font-normal leading-[0.98] tracking-[-0.02em]">
              {c.title} <span className="chip-glow font-sans text-[0.62em] font-medium tracking-[-0.04em]">{c.accent}</span>
            </h1>
            <p className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-cream/65 md:text-xl">{c.subtitle}</p>
            <CtaButton tone="light">{c.cta}</CtaButton>
          </motion.div>
          <motion.div {...blurReveal(0.15, 24, 0.97)} className="relative mx-auto mt-12 h-72 max-w-xl md:h-96">
            <Suspense fallback={null}>
              <Object3D variant="hub" className="absolute inset-0" />
            </Suspense>
          </motion.div>
        </section>

        <section className="px-6 pb-24 md:pb-32">
          <div className="mx-auto grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {c.tools.map((tool, i) => {
              const Mark = MARKS[i];
              return (
                <motion.div
                  key={tool.name}
                  {...blurReveal(i * 0.07, 28, 0.97)}
                  className="group relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] p-7 transition-colors duration-500 hover:bg-white/[0.06]"
                >
                  <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
                  <Mark className="mb-10 h-10 w-10 text-cream/85 transition-transform duration-500 ease-silk group-hover:scale-105" />
                  <h3 className="mb-2 text-xl font-medium tracking-[-0.03em]">{tool.name}</h3>
                  <p className="text-[15px] leading-relaxed text-cream/55">{tool.desc}</p>
                </motion.div>
              );
            })}
            <motion.div
              {...blurReveal(0.21, 28, 0.97)}
              className="relative overflow-hidden rounded-3xl border border-dashed border-white/15 p-7"
            >
              <Plus className="mb-10 h-10 w-10 text-cream/50" strokeWidth={1.2} />
              <h3 className="mb-2 text-xl font-medium tracking-[-0.03em]">{c.more.name}</h3>
              <p className="text-[15px] leading-relaxed text-cream/55">{c.more.desc}</p>
            </motion.div>
          </div>
        </section>

        <section className="px-6 pb-24 md:pb-32">
          <div className="mx-auto grid max-w-5xl items-start gap-12 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
            <motion.div {...blurReveal()}>
              <h2 className="h-display mb-10 text-4xl md:text-5xl">{c.stepsTitle}</h2>
              <ol className="space-y-8">
                {c.steps.map((step, i) => (
                  <li key={step.title} className="flex gap-5">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/15 text-xs text-cream/70">
                      {i + 1}
                    </span>
                    <span>
                      <span className="block text-lg font-medium tracking-[-0.02em]">{step.title}</span>
                      <span className="mt-1 block text-[15px] leading-relaxed text-cream/55">{step.desc}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </motion.div>

            <motion.div {...blurReveal(0.1, 32, 0.97)} className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03]">
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-3.5">
                <span className="text-xs text-cream/55">{c.promptsTitle}</span>
                <span className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-cream/45">
                  {c.promptsBadge}
                </span>
              </div>
              <ul className="space-y-3 p-5">
                {c.prompts.map((prompt, i) => (
                  <motion.li
                    key={prompt}
                    initial={{ opacity: 0, y: 12 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-60px" }}
                    transition={{ duration: 0.6, delay: 0.2 + i * 0.18, ease: [0.16, 1, 0.3, 1] }}
                    className="rounded-2xl rounded-bl-md bg-white/[0.07] px-4 py-3 text-[13px] leading-relaxed text-cream/85 text-xs"
                  >
                    <span className="mr-2 text-beige-light">›</span>
                    {prompt}
                  </motion.li>
                ))}
              </ul>
            </motion.div>
          </div>
        </section>

        <section className="px-6 pb-28 text-center md:pb-36">
          <motion.div {...blurReveal()} className="mx-auto max-w-3xl">
            <h2 className="h-display mb-10 text-balance text-4xl md:text-6xl">
              {c.closingTitle} <span className="accent-serif text-cream/80">{c.closingAccent}</span>
            </h2>
            <CtaButton tone="ghost">{c.cta}</CtaButton>
          </motion.div>
        </section>
      </main>
      <Footer />
    </div>
  );
};

export default McpPage;
