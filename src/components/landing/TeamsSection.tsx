import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { Suspense, lazy } from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "@/lib/i18n";
import { ROLE_PATHS, type RoleKey } from "@/lib/landing-roles";
import { blurReveal } from "@/lib/scrollReveal";
import type { Object3DVariant } from "./Object3D";

const Object3D = lazy(() => import("./Object3D"));

const TEAMS: { role: RoleKey; object: Object3DVariant; tone: string}[] = [
  { role: "sdr", object: "handset", tone: "bg-tone-sand" },
  { role: "ae", object: "briefcase", tone: "bg-tone-sage" },
  { role: "manager", object: "clipboard", tone: "bg-tone-clay" },
  { role: "field", object: "whatsapp", tone: "bg-tone-stone" },
  { role: "revops", object: "database", tone: "bg-tone-sand" },
];

const TeamsSection = () => {
  const { t } = useLanguage();
  const titles: { title: string }[] = t.nav.menus.teams;
  const descriptions: string[] = t.teams.cards;

  return (
    <section className="relative bg-white py-28 md:py-36">
      <div className="container mx-auto px-6">
        <motion.div {...blurReveal()} className="mx-auto mb-16 max-w-3xl text-center">
          <span className="section-label mb-6">04 — {t.teams.label}</span>
          <h2 className="h-display mb-6 text-balance text-4xl text-foreground md:text-6xl">
            {t.teams.title1} <span className="accent-serif">{t.teams.title2}</span>
          </h2>
          <p className="text-lg leading-relaxed text-muted-foreground md:text-xl">{t.teams.subtitle}</p>
        </motion.div>

        <div className="mx-auto grid max-w-6xl gap-5 md:grid-cols-6">
          {TEAMS.map(({ role, object, tone }, i) => (
            <motion.div key={role} {...blurReveal(i * 0.07, 28, 0.96)} className={i < 3 ? "md:col-span-2" : "md:col-span-3"}>
              <Link
                to={ROLE_PATHS[role]}
                className={`${tone} group flex h-full flex-col justify-between gap-4 rounded-[28px] border border-white/70 p-7 transition-shadow duration-500 ease-silk hover:shadow-float`}
              >
                <span className="flex items-start justify-between">
                  <span className="relative -mb-3 -ml-3 block h-36 w-40">
                    <Suspense fallback={null}>
                      <Object3D variant={object} className="absolute inset-0" />
                    </Suspense>
                  </span>
                  <ArrowUpRight className="h-5 w-5 text-foreground/40 transition-all duration-500 ease-silk group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-foreground" />
                </span>
                <span>
                  <span className="mb-2 block text-xl font-medium tracking-[-0.03em] text-foreground">{titles[i].title}</span>
                  <span className="block text-[15px] leading-relaxed text-foreground/70">{descriptions[i]}</span>
                </span>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default TeamsSection;
