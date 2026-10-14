import { Suspense, lazy, useEffect } from "react";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";
import { RoleMockView } from "@/components/landing/mocks";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import { useLanguage } from "@/lib/i18n";
import { ROLE_OBJECT, rolesCopy, rolesUi } from "@/lib/landing-roles";
import type { RoleKey } from "@/lib/landing-roles";
import { blurReveal } from "@/lib/scrollReveal";

const Object3D = lazy(() => import("@/components/landing/Object3D"));

const TONES = ["bg-tone-sand", "bg-tone-sage", "bg-tone-clay", "bg-tone-stone", "bg-tone-sand"];

const RoleLandingPage = ({ role }: { role: RoleKey }) => {
  const { language } = useLanguage();
  const copy = rolesCopy[language][role];
  const ui = rolesUi[language];

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [role]);

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        <section className="bg-mesh-gradient px-6 pb-20 pt-40 text-center md:pb-28 md:pt-48">
          <motion.div {...blurReveal(0, 20, 0.98)} className="mx-auto max-w-4xl">
            <div className="relative mx-auto mb-2 h-48 w-56">
              <Suspense fallback={null}>
                <Object3D variant={ROLE_OBJECT[role]} className="absolute inset-0" />
              </Suspense>
            </div>
            <span className="section-label mb-8">{copy.eyebrow}</span>
            <h1 className="mb-7 text-balance text-[clamp(2.75rem,6.5vw,5rem)] font-semibold leading-[0.98] tracking-[-0.04em] text-foreground">
              {copy.title} <span className="accent-serif">{copy.accent}</span>
            </h1>
            <p className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-muted-foreground md:text-xl">{copy.subtitle}</p>
            <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
              <a
                href={DEMO_BOOKING_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-glow transition-snap group inline-flex w-full items-center justify-center gap-3 rounded-full bg-beige py-3 pl-7 pr-3 text-sm font-semibold text-cream hover:bg-beige-dark active:scale-[0.98] sm:w-auto"
              >
                {ui.demo}
                <span className="flex size-9 items-center justify-center rounded-full bg-cream text-beige transition-transform duration-500 ease-silk group-hover:translate-x-0.5">
                  <ArrowRight className="h-4 w-4" />
                </span>
              </a>
            </div>
          </motion.div>
        </section>

        <section className="bg-white py-20 md:py-28">
          <div className="container mx-auto max-w-6xl space-y-24 px-6 md:space-y-36">
            {copy.sections.map((section, i) => (
              <article key={section.step} className="grid items-center gap-10 lg:grid-cols-2 lg:gap-20">
                <motion.div {...blurReveal(0, 20, 0.98)} className={i % 2 === 1 ? "lg:order-2" : undefined}>
                  <span className="mb-5 inline-flex items-center rounded-full border border-border bg-white px-3 py-1 text-xs font-medium text-beige">
                    {section.step}
                  </span>
                  <h2 className="mb-4 text-balance text-3xl font-semibold leading-[1.1] tracking-tighter text-foreground md:text-4xl">
                    {section.title}
                  </h2>
                  <p className="max-w-md text-lg leading-relaxed text-muted-foreground">{section.desc}</p>
                </motion.div>
                <motion.div
                  {...blurReveal(0.1, 32, 0.96)}
                  className={`${TONES[i % TONES.length]} rounded-[28px] border border-white/70 p-4 shadow-card md:p-8 ${
                    i % 2 === 1 ? "lg:order-1" : ""
                  }`}
                >
                  <RoleMockView mock={section.mock} sample={ui.sample} />
                </motion.div>
              </article>
            ))}
          </div>
        </section>

        <section className="bg-ink px-6 py-28 text-center text-cream md:py-36">
          <motion.div {...blurReveal()} className="mx-auto max-w-3xl">
            <h2 className="mb-10 text-balance text-4xl font-semibold leading-[1.05] tracking-tighter md:text-6xl">
              {copy.closingTitle} <span className="accent-serif text-cream/80">{copy.closingAccent}</span>
            </h2>
            <a
              href={DEMO_BOOKING_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-center justify-center gap-3 rounded-full bg-cream py-3 pl-7 pr-3 text-sm font-semibold text-ink transition-all duration-500 ease-silk hover:bg-white active:scale-[0.98]"
            >
              {ui.closingCta}
              <span className="flex size-9 items-center justify-center rounded-full bg-beige text-cream transition-transform duration-500 ease-silk group-hover:translate-x-0.5">
                <ArrowRight className="h-4 w-4" />
              </span>
            </a>
          </motion.div>
        </section>
      </main>
      <Footer />
    </div>
  );
};

export default RoleLandingPage;
