import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { CallRecordingsSettings } from "@/components/dashboard/settings/CallRecordingsSettings";
import { CallerIdSettings } from "@/components/dashboard/settings/CallerIdSettings";
import { VocifyCallingSettings } from "@/components/dashboard/settings/VocifyCallingSettings";
import { useDesktopCalling } from "@/features/desktop/useDesktopCalling";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const CallingSection = () => {
  const { hash } = useLocation();

  useEffect(() => {
    if (hash !== "#caller-id") return;
    document.getElementById("caller-id")?.scrollIntoView({ block: "start" });
  }, [hash]);

  // The desktop app: whether its island calls through Vocify or on the rep's own phone.
  const { calling } = useDesktopCalling();

  return (
    <div className="space-y-6">
      {calling ? (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
          <VocifyCallingSettings />
        </div>
      ) : null}
      <div
        id="caller-id"
        className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} scroll-mt-6 p-6 md:p-8`}
      >
        <CallerIdSettings />
      </div>
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
        <CallRecordingsSettings />
      </div>
    </div>
  );
};

export default CallingSection;
