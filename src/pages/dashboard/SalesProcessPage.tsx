import { HosPageHeader } from "@/features/head-of-sales/HosFilters";
import PlaybooksSection from "@/features/playbooks/components/PlaybooksSection";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * Proceso de venta: the process itself, what Vocify checks on every call. Whether it is working
 * (process health, objections) is read in Equipo, next to the people it is about.
 */
export default function SalesProcessPage() {
  const { t } = useLanguage();
  const p = t.product;

  return (
    <main className={`max-w-5xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <HosPageHeader title={p.hosProcessTitle} subtitle={p.hosProcessPageSubtitle} />
      <section aria-label={p.pb2.sectionTitle} id="playbooks">
        <PlaybooksSection />
      </section>
    </main>
  );
}
