import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { CallerIdSettings } from "@/components/dashboard/settings/CallerIdSettings";
import { TranscriptionLanguageSettings } from "@/components/dashboard/settings/TranscriptionLanguageSettings";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const CallingSection = () => {
  const { hash } = useLocation();

  useEffect(() => {
    if (hash !== "#caller-id") return;
    document.getElementById("caller-id")?.scrollIntoView({ block: "start" });
  }, [hash]);

  return (
    <div className="space-y-6">
      <div
        id="caller-id"
        className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} scroll-mt-6 p-6 md:p-8`}
      >
        <CallerIdSettings />
      </div>
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
        <TranscriptionLanguageSettings />
      </div>
    </div>
  );
};

export default CallingSection;
