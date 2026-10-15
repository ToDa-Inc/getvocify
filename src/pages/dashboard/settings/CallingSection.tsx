import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { CallRecordingsSettings } from "@/components/dashboard/settings/CallRecordingsSettings";
import { CallerIdSettings } from "@/components/dashboard/settings/CallerIdSettings";
import { VocifyCallingSettings } from "@/components/dashboard/settings/VocifyCallingSettings";
import { useDesktopCalling } from "@/features/desktop/useDesktopCalling";
import { SettingsSection } from "@/components/ui/settings-card";
import { useLanguage } from "@/lib/i18n";

const CallingSection = () => {
  const { t } = useLanguage();
  const { hash } = useLocation();

  // The desktop app: whether its island calls through Vocify or on the rep's own phone.
  const { calling } = useDesktopCalling();

  // A link to one card (#caller-id, #vocify-calling); the calling card only exists once the desktop app answered.
  useEffect(() => {
    if (hash !== "#caller-id" && hash !== "#vocify-calling") return;
    document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [hash, calling]);

  return (
    <div className="mx-auto max-w-[680px]">
      <SettingsSection label={t.product.settingsNavCalling}>
        {calling ? (
          <div id="vocify-calling" className="scroll-mt-6">
            <VocifyCallingSettings />
          </div>
        ) : null}
        <div id="caller-id" className="scroll-mt-6 py-5">
          <CallerIdSettings />
        </div>
        <CallRecordingsSettings />
      </SettingsSection>
    </div>
  );
};

export default CallingSection;
