import { THEME_TOKENS } from "@/lib/theme/tokens";
import { TodayPanel } from "./TodayPanel";

export function RepHome() {
  return (
    <div className={`max-w-3xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      <TodayPanel />
    </div>
  );
}
