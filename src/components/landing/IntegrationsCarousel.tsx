import { useLanguage } from "@/lib/i18n";
import CrmStack from "./CrmStack";

const IntegrationsCarousel = () => {
  const { t } = useLanguage();

  return (
    <div className="w-full border-t border-white/10 py-14">
      <div className="container mx-auto px-6">
        <p className="mb-8 text-center text-base font-medium tracking-tight text-cream/55">{t.integrations.title}</p>
        <CrmStack more={t.integrations.more} tone="dark" />
      </div>
    </div>
  );
};

export default IntegrationsCarousel;
