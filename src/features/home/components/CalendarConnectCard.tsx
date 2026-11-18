import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { toast } from "sonner";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { calendarApi, calendarKeys, type CalendarProvider } from "@/lib/api/calendar";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import googleCalendarLogo from "@/assets/brands/google-calendar.svg";
import outlookLogo from "@/assets/brands/outlook.svg";

const PROVIDER: Record<CalendarProvider, { name: string; logo: string }> = {
  google: { name: "Google Calendar", logo: googleCalendarLogo },
  microsoft: { name: "Outlook", logo: outlookLogo },
};

const dismissedKey = (userId: string) => `vocify.calendarPrompt.dismissed.${userId}`;

function readDismissed(userId: string | undefined): boolean {
  if (!userId) return false;
  try {
    return localStorage.getItem(dismissedKey(userId)) === "1";
  } catch {
    return false;
  }
}

/**
 * The first step after signing up, on Home until it is done or put off: a meeting needs the calendar to know who it is
 * with, so Vocify can save it on the right contact and announce it a minute before. Gone once a calendar is connected
 * (Settings › Calendar keeps it after that).
 */
export function CalendarConnectCard() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const enabled = Boolean(user?.company?.features?.includes("RECALL_BOT_ENABLED"));
  const [dismissed, setDismissed] = useState(() => readDismissed(user?.id));
  const [redirecting, setRedirecting] = useState<CalendarProvider | null>(null);
  const { data } = useQuery({ queryKey: calendarKeys.state, queryFn: calendarApi.get, enabled: enabled && !dismissed });

  if (!enabled || dismissed || !data || data.connection || !data.providers.length) return null;

  const connect = async (provider: CalendarProvider) => {
    setRedirecting(provider);
    try {
      const { redirect_url } = await calendarApi.authorizeUrl(provider);
      window.location.href = redirect_url;
    } catch {
      setRedirecting(null);
      toast.error(t.product.calendarConnectFailed);
    }
  };

  const later = () => {
    try {
      if (user?.id) localStorage.setItem(dismissedKey(user.id), "1");
    } catch {
      // Storage blocked: it asks again next time.
    }
    setDismissed(true);
  };

  return (
    <section className={`${THEME_TOKENS.radius.container} relative border border-border/60 bg-card p-5 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="absolute right-2 top-2">
        <IconAction label={t.product.calendarPromptLater} onClick={later}>
          <X />
        </IconAction>
      </div>
      <p className="pr-8 text-[15px] text-foreground">{t.product.calendarPromptTitle}</p>
      <p className={`mt-1 pr-8 ${THEME_TOKENS.typography.body}`}>{t.product.calendarPromptBody}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {data.providers.map((provider) => (
          <button
            key={provider}
            type="button"
            disabled={redirecting !== null}
            onClick={() => void connect(provider)}
            className="inline-flex h-9 items-center gap-2 rounded-full border border-border/70 bg-background px-3.5 text-[13px] font-medium text-foreground transition-colors duration-150 hover:bg-secondary/60 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
          >
            {redirecting === provider ? <VocifySpinner /> : <img src={PROVIDER[provider].logo} alt="" className="h-4 w-4 object-contain" />}
            {PROVIDER[provider].name}
          </button>
        ))}
      </div>
    </section>
  );
}
