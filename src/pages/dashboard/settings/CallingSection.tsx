import { CallerIdSettings } from "@/components/dashboard/settings/CallerIdSettings";
import { TranscriptionLanguageSettings } from "@/components/dashboard/settings/TranscriptionLanguageSettings";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const CallingSection = () => {
  return (
    <div className="space-y-6">
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
        <TranscriptionLanguageSettings />
      </div>
      <div
        id="caller-id"
        className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} scroll-mt-6 p-6 md:p-8`}
      >
        <CallerIdSettings />
      </div>
    </div>
  );
};

export default CallingSection;
